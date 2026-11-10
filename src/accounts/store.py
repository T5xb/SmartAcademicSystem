"""Reads and writes for users, sessions, saved chats, profiles and settings."""

import json
import os
import secrets
from datetime import datetime, timedelta, timezone

import functools

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from .db import get_engine, now_iso
from .security import hash_password, hash_token, new_token

ROLES = ("student", "advisor", "admin")

MAX_CHATS_PER_USER = 200
MAX_CHAT_BYTES = 400_000
MAX_PROFILE_BYTES = 200_000

# The accounts every installation starts with. Their password comes from
# PRESET_PASSWORD (src/.env). They are only created when missing, so a
# password changed later, or a disabled account, is never reset by a restart.
PRESET_ACCOUNTS = [
    {"username": "admin", "name": "مدير النظام", "role": "admin"},
    {"username": "advisor", "name": "د. خالد العتيبي", "role": "advisor"},
    {"username": "441000001", "name": "أحمد الراشد", "role": "student"},
    {"username": "441000002", "name": "سارة القحطاني", "role": "student"},
    {"username": "441000003", "name": "محمد الحربي", "role": "student"},
]
DEFAULT_PRESET_PASSWORD = "test12345"


class UsernameTaken(Exception):
    pass


def _retry(fn):
    """Run again once when the connection was lost (the pooler closes idle
    ones). Every function here is one transaction, so nothing is half done."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except OperationalError:
            return fn(*args, **kwargs)

    return wrapper


@_retry
def _rows(query: str, params: dict | None = None) -> list:
    # Autocommit: a read needs no transaction, which saves two round trips
    # (BEGIN and ROLLBACK) to a database on another continent.
    with get_engine().connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        return conn.execute(text(query), params or {}).all()


def _row(query: str, params: dict | None = None):
    rows = _rows(query, params)
    return rows[0] if rows else None


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def _user(row) -> dict | None:
    if row is None:
        return None
    user = dict(row._mapping)
    user["active"] = bool(user["active"])
    user["must_change_password"] = bool(user["must_change_password"])
    return user


def public_user(user: dict) -> dict:
    """A user without the password hash, as the API returns it."""
    return {k: v for k, v in user.items() if k != "password_hash"}


# ------------------------------------------------------------------ users


def create_user(
    username: str, name: str, role: str, password: str, must_change_password: bool = False
) -> dict:
    if role not in ROLES:
        raise ValueError(f"Unknown role: {role}")
    user = {
        "id": secrets.token_hex(8),
        "username": normalize_username(username),
        "name": name.strip(),
        "role": role,
        "password_hash": hash_password(password),
        "active": 1,
        "must_change_password": int(must_change_password),
        "created_at": now_iso(),
    }
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO sas_users (id, username, name, role, password_hash, active,"
                    " must_change_password, created_at) VALUES (:id, :username, :name, :role,"
                    " :password_hash, :active, :must_change_password, :created_at)"
                ),
                user,
            )
    except IntegrityError as e:
        raise UsernameTaken(user["username"]) from e
    return _user_by("id", user["id"])


def _user_by(column: str, value: str) -> dict | None:
    return _user(_row(f"SELECT * FROM sas_users WHERE {column} = :v", {"v": value}))


def get_user(user_id: str) -> dict | None:
    return _user_by("id", user_id)


def get_user_by_username(username: str) -> dict | None:
    return _user_by("username", normalize_username(username))


def list_users(role: str | None = None) -> list[dict]:
    query = "SELECT * FROM sas_users"
    params = {}
    if role:
        query += " WHERE role = :role"
        params["role"] = role
    return [_user(r) for r in _rows(query + " ORDER BY role, name", params)]


@_retry
def update_user(user_id: str, *, name: str | None = None, active: bool | None = None) -> None:
    with get_engine().begin() as conn:
        if name is not None:
            conn.execute(
                text("UPDATE sas_users SET name = :name WHERE id = :id"),
                {"name": name.strip(), "id": user_id},
            )
        if active is not None:
            conn.execute(
                text("UPDATE sas_users SET active = :active WHERE id = :id"),
                {"active": int(active), "id": user_id},
            )
            if not active:
                conn.execute(text("DELETE FROM sas_sessions WHERE user_id = :id"), {"id": user_id})


@_retry
def set_password(
    user_id: str, password: str, *, must_change_password: bool, keep_token: str | None = None
) -> None:
    """Change a password and sign the user out everywhere (except `keep_token`)."""
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE sas_users SET password_hash = :hash, must_change_password = :must"
                " WHERE id = :id"
            ),
            {"hash": hash_password(password), "must": int(must_change_password), "id": user_id},
        )
        conn.execute(
            text("DELETE FROM sas_sessions WHERE user_id = :id AND token_hash <> :keep"),
            {"id": user_id, "keep": hash_token(keep_token) if keep_token else ""},
        )


def seed_preset_accounts() -> list[str]:
    """Create the preset accounts that don't exist yet; returns their usernames."""
    password = os.getenv("PRESET_PASSWORD", "").strip() or DEFAULT_PRESET_PASSWORD
    created = []
    for account in PRESET_ACCOUNTS:
        if get_user_by_username(account["username"]) is None:
            create_user(password=password, **account)
            created.append(account["username"])
    return created


# --------------------------------------------------------------- sessions


@_retry
def create_session(user_id: str, lifetime: timedelta) -> str:
    token = new_token()
    now = datetime.now(timezone.utc)
    with get_engine().begin() as conn:
        # Sessions that ran out are cleared here, so the table doesn't grow.
        conn.execute(
            text("DELETE FROM sas_sessions WHERE expires_at < :now"),
            {"now": now.isoformat(timespec="seconds")},
        )
        conn.execute(
            text("INSERT INTO sas_sessions (token_hash, user_id, expires_at) VALUES (:t, :u, :e)"),
            {"t": hash_token(token), "u": user_id, "e": (now + lifetime).isoformat(timespec="seconds")},
        )
    return token


def session_user(token: str) -> dict | None:
    """The active user this session token belongs to, or None."""
    row = _row(
        "SELECT u.* FROM sas_sessions s JOIN sas_users u ON u.id = s.user_id"
        " WHERE s.token_hash = :t AND s.expires_at > :now AND u.active = 1",
        {"t": hash_token(token), "now": now_iso()},
    )
    return _user(row)


@_retry
def delete_session(token: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM sas_sessions WHERE token_hash = :t"), {"t": hash_token(token)})


# ------------------------------------------------------------ saved chats


def list_chats(user_id: str) -> list[dict]:
    rows = _rows(
        "SELECT data FROM sas_chats WHERE user_id = :u ORDER BY updated_at DESC", {"u": user_id}
    )
    return [json.loads(r[0]) for r in rows]


@_retry
def save_chat(user_id: str, chat_id: str, chat: dict) -> None:
    data = json.dumps(chat, ensure_ascii=False)
    if len(data.encode("utf-8")) > MAX_CHAT_BYTES:
        raise ValueError("This chat is too long to save.")
    params = {"u": user_id, "id": chat_id, "data": data, "now": now_iso()}
    with get_engine().begin() as conn:
        updated = conn.execute(
            text("UPDATE sas_chats SET data = :data, updated_at = :now WHERE user_id = :u AND id = :id"),
            params,
        )
        if updated.rowcount:
            return
        count = conn.execute(
            text("SELECT count(*) FROM sas_chats WHERE user_id = :u"), {"u": user_id}
        ).scalar()
        if count >= MAX_CHATS_PER_USER:
            # The oldest chat makes room, as a chat list would scroll it away.
            conn.execute(
                text(
                    "DELETE FROM sas_chats WHERE user_id = :u AND id = (SELECT id FROM sas_chats"
                    " WHERE user_id = :u ORDER BY updated_at ASC LIMIT 1)"
                ),
                {"u": user_id},
            )
        conn.execute(
            text("INSERT INTO sas_chats (user_id, id, data, updated_at) VALUES (:u, :id, :data, :now)"),
            params,
        )


@_retry
def delete_chat(user_id: str, chat_id: str | None = None) -> None:
    """Delete one chat, or all of the user's chats when `chat_id` is None."""
    query = "DELETE FROM sas_chats WHERE user_id = :u"
    params = {"u": user_id}
    if chat_id is not None:
        query += " AND id = :id"
        params["id"] = chat_id
    with get_engine().begin() as conn:
        conn.execute(text(query), params)


def count_chats(user_id: str) -> int:
    return int(_row("SELECT count(*) FROM sas_chats WHERE user_id = :u", {"u": user_id})[0] or 0)


# ---------------------------------------------------------------- profiles


def get_profile(user_id: str) -> dict:
    row = _row("SELECT data FROM sas_profiles WHERE user_id = :u", {"u": user_id})
    return json.loads(row[0]) if row else {}


def students_with_profiles() -> list[tuple[dict, dict]]:
    """Every student with their profile, in one query."""
    rows = _rows(
        "SELECT u.*, p.data AS profile_data FROM sas_users u"
        " LEFT JOIN sas_profiles p ON p.user_id = u.id"
        " WHERE u.role = 'student' ORDER BY u.name"
    )
    result = []
    for row in rows:
        user = _user(row)
        profile = json.loads(user.pop("profile_data") or "{}")
        result.append((user, profile))
    return result


@_retry
def update_profile(user_id: str, changes: dict) -> dict:
    """Merge `changes` into the profile's top-level keys and return the result."""
    profile = get_profile(user_id)
    profile.update(changes)
    data = json.dumps(profile, ensure_ascii=False)
    if len(data.encode("utf-8")) > MAX_PROFILE_BYTES:
        raise ValueError("The profile is too large to save.")
    params = {"u": user_id, "data": data, "now": now_iso()}
    with get_engine().begin() as conn:
        updated = conn.execute(
            text("UPDATE sas_profiles SET data = :data, updated_at = :now WHERE user_id = :u"),
            params,
        )
        if not updated.rowcount:
            conn.execute(
                text("INSERT INTO sas_profiles (user_id, data, updated_at) VALUES (:u, :data, :now)"),
                params,
            )
    return profile


# ------------------------------------------------------------------- meta


def get_meta(key: str, default: str = "") -> str:
    row = _row("SELECT value FROM sas_meta WHERE key = :k", {"k": key})
    return row[0] if row else default


@_retry
def set_meta(key: str, value: str) -> None:
    with get_engine().begin() as conn:
        updated = conn.execute(
            text("UPDATE sas_meta SET value = :v WHERE key = :k"), {"k": key, "v": value}
        )
        if not updated.rowcount:
            conn.execute(text("INSERT INTO sas_meta (key, value) VALUES (:k, :v)"), {"k": key, "v": value})
