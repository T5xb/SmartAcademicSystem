"""FastAPI dependencies: who is signed in, and which roles a route allows."""

import time

from fastapi import Depends, HTTPException, Request

from . import store

SESSION_COOKIE = "sas_session"

# A session is looked up in the database (a network round trip to Supabase)
# at most once per this many seconds; sign-out and account changes clear it.
_CACHE_SECONDS = 30
_cache: dict[str, tuple[float, dict]] = {}


def forget_sessions() -> None:
    _cache.clear()


def _lookup(token: str) -> dict | None:
    now = time.monotonic()
    hit = _cache.get(token)
    if hit and now - hit[0] < _CACHE_SECONDS:
        return hit[1]
    user = store.session_user(token)
    if user is None:
        _cache.pop(token, None)
        return None
    if len(_cache) > 2000:
        _cache.clear()
    _cache[token] = (now, user)
    return user


def signed_in_user(request: Request) -> dict:
    """The signed-in user, even one who still has to change their password."""
    token = request.cookies.get(SESSION_COOKIE)
    user = _lookup(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return user


def current_user(user: dict = Depends(signed_in_user)) -> dict:
    """The signed-in user; blocked until a temporary password is replaced."""
    if user["must_change_password"]:
        raise HTTPException(status_code=403, detail="Change your temporary password first.")
    return user


def require_roles(*roles: str):
    def check(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Your account can't open this.")
        return user

    return check


require_student = require_roles("student")
require_advisor = require_roles("advisor", "admin")
require_admin = require_roles("admin")
