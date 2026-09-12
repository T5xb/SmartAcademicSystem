"""
Vector store access: Supabase Postgres + pgvector.

Used by src/generate.py to build the index and by the app to query it.
See ARCHITECTURE.md §4.3-4.4 for why Postgres over Chroma, why the
session pooler is mandatory here, and why there is no ANN index.
"""

import logging
import os
from urllib.parse import urlsplit, urlunsplit

from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import create_engine, text

logger = logging.getLogger("uvicorn")

# Where source documents (PDFs, docx, txt...) live.
DATA_DIR = os.environ.get("DATA_DIR", "docs")

PGVECTOR_TABLE = os.environ.get("PGVECTOR_TABLE", "academic_advising")

# Must match the embedding model's vector width (bge-m3 = 1024). pgvector
# fixes this when the column is created, so changing the embedding model
# means re-running `generate`, not a migration.
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))

# PGVectorStore prefixes the configured name (`tablename = "data_%s"`), so
# our own SQL has to target the prefixed name.
PGVECTOR_REAL_TABLE = f"data_{PGVECTOR_TABLE}"


def _require_db_url() -> str:
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError(
            "SUPABASE_DB_URL is missing in src/.env. Copy the Session "
            "pooler connection string from Supabase -> Connect -> Direct "
            "connection -> Session pooler."
        )
    return url


def sqlalchemy_urls(db_url: str | None = None) -> tuple[str, str]:
    """
    Turn one Supabase URI into the (sync, async) URLs PGVectorStore needs.

    Three adjustments, each a silent failure if skipped:

    1. Pin the drivers this project installs (psycopg2 sync, asyncpg
       async); Supabase hands out a bare postgresql:// URI, and "postgres"
       is a legacy alias SQLAlchemy rejects outright.
    2. Supabase URIs often carry `?sslmode=require`. psycopg2 accepts it,
       asyncpg raises on it, so the async URL drops the query string.
       asyncpg still negotiates TLS, so the connection stays encrypted.
    3. `prepared_statement_cache_size=0` because the transaction-mode
       pooler (port 6543) cannot hold per-session prepared statements,
       which asyncpg uses by default. Without this, concurrent requests
       hit intermittent "prepared statement already exists" errors — and
       the app's query path is async. Harmless on port 5432 and on direct
       connections, so it is applied unconditionally.
    """
    parts = urlsplit(db_url or _require_db_url())
    netloc, path = parts.netloc, parts.path
    sync = urlunsplit(("postgresql+psycopg2", netloc, path, parts.query, ""))
    async_ = urlunsplit(
        ("postgresql+asyncpg", netloc, path, "prepared_statement_cache_size=0", "")
    )
    return sync, async_


def get_vector_store(perform_setup: bool = True) -> PGVectorStore:
    """
    Build the PGVectorStore handle.

    perform_setup=True creates the table, pgvector extension and index if
    absent — wanted when indexing, a no-op once they exist.
    """
    sync_url, async_url = sqlalchemy_urls()
    return PGVectorStore.from_params(
        connection_string=sync_url,
        async_connection_string=async_url,
        table_name=PGVECTOR_TABLE,
        embed_dim=EMBED_DIM,
        perform_setup=perform_setup,
        # JSONB so metadata can be indexed later; Postgres cannot index
        # plain JSON for containment.
        use_jsonb=True,
        # No hnsw_kwargs on purpose: pgvector then does an exact cosine
        # scan, which at 118 chunks is faster than an index probe and more
        # accurate (HNSW is approximate and could miss the true nearest
        # chunk — a wrong-source risk for a cited answer). At thousands of
        # chunks, add:
        #   hnsw_kwargs={"hnsw_m": 16, "hnsw_ef_construction": 64,
        #                "hnsw_ef_search": 40,
        #                "hnsw_dist_method": "vector_cosine_ops"}
        # and re-run `generate`.
    )


def count_indexed_chunks() -> int:
    """Rows in the vector table, or 0 if it doesn't exist yet."""
    sync_url, _ = sqlalchemy_urls()
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(f'SELECT count(*) FROM "{PGVECTOR_REAL_TABLE}"')
            )
            return int(result.scalar() or 0)
    except Exception:
        # Not created yet — treated as empty so callers can say "run
        # generate" instead of surfacing a raw Postgres error.
        logger.info(
            f"Vector table '{PGVECTOR_REAL_TABLE}' not readable yet -- "
            "treating as empty."
        )
        return 0
    finally:
        engine.dispose()


def reset_vector_table() -> None:
    """
    Drop the vector table so a rebuild starts clean.

    Keeps the behaviour the Chroma version had: re-running `generate` must
    not accumulate duplicate or stale chunks. The table is recreated by
    the next setup pass.
    """
    sync_url, _ = sqlalchemy_urls()
    engine = create_engine(sync_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS "{PGVECTOR_REAL_TABLE}"'))
        logger.info(f"Dropped existing vector table '{PGVECTOR_REAL_TABLE}'")
    finally:
        engine.dispose()


def get_index():
    """The queryable index, or None if nothing has been indexed yet."""
    if count_indexed_chunks() == 0:
        return None
    logger.info(f"Loading index from Postgres table '{PGVECTOR_REAL_TABLE}'...")
    # perform_setup=False: the table exists at query time, and DDL here
    # would need privileges a read-only app role shouldn't have.
    index = VectorStoreIndex.from_vector_store(get_vector_store(perform_setup=False))
    logger.info("Finished loading index from Postgres")
    return index
