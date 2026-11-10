"""
The accounts tables. They live in the same Supabase Postgres database as the
document index (SUPABASE_DB_URL); ACCOUNTS_DB_URL overrides that, which the
tests use to run on a throwaway SQLite database.

The SQL is kept to what both databases understand: text columns, JSON stored
as text, ISO-8601 UTC timestamps (which sort correctly as strings).
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

TABLES = ("sas_users", "sas_sessions", "sas_chats", "sas_profiles", "sas_meta")

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS sas_users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        must_change_password INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sas_sessions (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sas_chats (
        user_id TEXT NOT NULL,
        id TEXT NOT NULL,
        data TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sas_profiles (
        user_id TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sas_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
]

logger = logging.getLogger("gp2-accounts")

_engine: Engine | None = None
_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _database_url() -> str:
    url = os.getenv("ACCOUNTS_DB_URL", "").strip()
    if url:
        return url
    # Imported here: src.index pulls in the whole retrieval stack.
    from src.index import sqlalchemy_urls

    return sqlalchemy_urls()[0]


def _create_engine(url: str) -> Engine:
    if url in ("sqlite://", "sqlite:///:memory:"):
        # One shared connection, so an in-memory database outlives a request.
        return create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    if url.startswith("sqlite"):
        return create_engine(url)
    # Small pool: the Supabase session pooler caps connections per project,
    # and the index uses some of them too.
    # No pre-ping: the database is far away, and a ping before every query
    # tripled its time. A connection the pooler dropped is retried instead
    # (store.py), and idle ones are replaced after four minutes.
    return create_engine(url, pool_size=3, max_overflow=2, pool_recycle=240)


def init_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for statement in _SCHEMA:
            conn.execute(text(statement))
        if engine.dialect.name == "postgresql":
            # Supabase exposes every table in `public` through its REST API.
            # Row-level security with no policy shuts that door; this server
            # connects as the table owner, which RLS does not restrict.
            for table in TABLES:
                conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))


def _init_with_retry(engine: Engine, attempts: int = 4) -> None:
    # The Supabase pooler now and then drops a new connection (seen right
    # after a restart, while the old process's connections are still closing).
    for attempt in range(1, attempts + 1):
        try:
            init_schema(engine)
            return
        except OperationalError:
            if attempt == attempts:
                raise
            logger.warning("Accounts database not reachable (try %d of %d)", attempt, attempts)
            time.sleep(2 * attempt)


def get_engine() -> Engine:
    """The accounts database, created (with its tables) on first use."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                engine = _create_engine(_database_url())
                _init_with_retry(engine)
                _engine = engine
    return _engine


def reset_engine() -> None:
    """Forget the engine, so the next call reconnects (used by the tests)."""
    global _engine
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
