"""Routes for sign-in, the signed-in user's own data, advisors and user management."""

import os
import re
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import store
from .deps import (
    SESSION_COOKIE,
    current_user,
    forget_sessions,
    require_admin,
    require_advisor,
    signed_in_user,
)
from .security import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    temporary_password,
    verify_password,
)

router = APIRouter(prefix="/api")

REMEMBERED_SESSION = timedelta(days=30)
BROWSER_SESSION = timedelta(hours=12)

# Wrong passwords allowed per address and account before a pause.
LOGIN_ATTEMPTS = int(os.getenv("LOGIN_ATTEMPTS", "8"))
LOGIN_WINDOW_SECONDS = 300
_failures: dict[str, deque] = defaultdict(deque)

USERNAME_PATTERN = r"^[A-Za-z0-9._@-]{3,60}$"
CHAT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

Password = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


# ------------------------------------------------------------------- auth


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    remember: bool = False


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Password


def _client_address(request: Request) -> str:
    # Same rule as the chat rate limit: through ngrok the visitor's own
    # address is the last entry of X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _recent_failures(key: str) -> deque:
    now = time.monotonic()
    if len(_failures) > 5000:
        _failures.clear()
    hits = _failures[key]
    while hits and now - hits[0] > LOGIN_WINDOW_SECONDS:
        hits.popleft()
    return hits


@router.post("/auth/login")
def login(req: LoginRequest, request: Request, response: Response):
    username = store.normalize_username(req.username)
    key = f"{_client_address(request)}|{username}"
    failures = _recent_failures(key)
    if LOGIN_ATTEMPTS > 0 and len(failures) >= LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=429, detail="Too many failed sign-in attempts. Try again in a few minutes."
        )

    user = store.get_user_by_username(username)
    if user is None or not verify_password(req.password, user["password_hash"]):
        failures.append(time.monotonic())
        # The same answer for an unknown account and a wrong password.
        raise HTTPException(status_code=401, detail="Wrong ID or password.")
    if not user["active"]:
        raise HTTPException(
            status_code=403, detail="This account is disabled. Contact the system administrator."
        )
    _failures.pop(key, None)

    lifetime = REMEMBERED_SESSION if req.remember else BROWSER_SESSION
    token = store.create_session(user["id"], lifetime)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        # Without "remember me" the cookie goes when the browser closes.
        max_age=int(lifetime.total_seconds()) if req.remember else None,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
        path="/",
    )
    return {"user": store.public_user(user)}


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        store.delete_session(token)
        forget_sessions()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user: dict = Depends(signed_in_user)):
    return {"user": store.public_user(user)}


@router.post("/auth/password")
def change_password(req: PasswordChange, request: Request, user: dict = Depends(signed_in_user)):
    if not verify_password(req.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="The current password is wrong.")
    if req.new_password == req.current_password:
        raise HTTPException(status_code=400, detail="Choose a password different from the current one.")
    store.set_password(
        user["id"], req.new_password, must_change_password=False,
        keep_token=request.cookies.get(SESSION_COOKIE),
    )
    forget_sessions()
    return {"ok": True}


# ---------------------------------------------------- my profile and chats


class ProfileUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    major: str | None = Field(default=None, max_length=120)
    level: str | None = Field(default=None, max_length=40)


class PlannerState(BaseModel):
    # The schedule page's own state (chosen courses, locks, time range...),
    # stored as it is and handed back on the next sign-in.
    planner: dict


class ChatSave(BaseModel):
    chat: dict


@router.get("/me/profile")
def my_profile(user: dict = Depends(current_user)):
    return {"user": store.public_user(user), "profile": store.get_profile(user["id"])}


@router.put("/me/profile")
def update_my_profile(req: ProfileUpdate, user: dict = Depends(current_user)):
    changes = {k: v.strip() for k, v in req.model_dump(exclude_none=True).items()}
    return {"profile": store.update_profile(user["id"], changes)}


@router.put("/me/planner")
def save_my_planner(req: PlannerState, user: dict = Depends(current_user)):
    try:
        store.update_profile(user["id"], {"planner": req.planner})
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    return {"ok": True}


@router.get("/me/chats")
def my_chats(user: dict = Depends(current_user)):
    return {"chats": store.list_chats(user["id"])}


@router.put("/me/chats/{chat_id}")
def save_my_chat(chat_id: str, req: ChatSave, user: dict = Depends(current_user)):
    if not CHAT_ID_PATTERN.match(chat_id):
        raise HTTPException(status_code=422, detail="Invalid chat id.")
    try:
        store.save_chat(user["id"], chat_id, req.chat)
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    return {"ok": True}


@router.delete("/me/chats/{chat_id}")
def delete_my_chat(chat_id: str, user: dict = Depends(current_user)):
    store.delete_chat(user["id"], chat_id)
    return {"ok": True}


@router.delete("/me/chats")
def delete_my_chats(user: dict = Depends(current_user)):
    store.delete_chat(user["id"])
    return {"ok": True}


# ---------------------------------------------------------------- advisor


def _student_summary(student: dict, profile: dict) -> dict:
    transcript = profile.get("transcript") or {}
    return {
        **store.public_user(student),
        "major": profile.get("major") or (transcript.get("student") or {}).get("major") or "",
        "gpa": transcript.get("gpa"),
        "earned_hours": transcript.get("earned_hours"),
        "completed_count": len(transcript.get("completed") or []),
        "has_transcript": bool(transcript),
    }


@router.get("/advisor/students")
def students(_: dict = Depends(require_advisor)):
    return {"students": [_student_summary(s, p) for s, p in store.students_with_profiles()]}


@router.get("/advisor/students/{student_id}")
def student(student_id: str, _: dict = Depends(require_advisor)):
    user = store.get_user(student_id)
    if user is None or user["role"] != "student":
        raise HTTPException(status_code=404, detail="Student not found.")
    # The academic profile and the saved schedule choices. Chat messages stay
    # private to the student; only their number is shown.
    return {
        "user": store.public_user(user),
        "profile": store.get_profile(student_id),
        "chat_count": store.count_chats(student_id),
    }


# ------------------------------------------------------- admin: accounts


class NewUser(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    role: Literal["student", "advisor"]


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None


@router.get("/admin/users")
def users(_: dict = Depends(require_admin)):
    return {"users": [store.public_user(u) for u in store.list_users()]}


@router.post("/admin/users", status_code=201)
def add_user(req: NewUser, _: dict = Depends(require_admin)):
    password = temporary_password()
    try:
        user = store.create_user(
            req.username, req.name, req.role, password, must_change_password=True
        )
    except store.UsernameTaken:
        raise HTTPException(status_code=409, detail="This ID is already used by another account.")
    # Shown to the admin once; only its hash is stored.
    return {"user": store.public_user(user), "temporary_password": password}


def _managed_user(user_id: str) -> dict:
    user = store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return user


@router.patch("/admin/users/{user_id}")
def edit_user(user_id: str, req: UserUpdate, admin: dict = Depends(require_admin)):
    user = _managed_user(user_id)
    if req.active is False and user["id"] == admin["id"]:
        raise HTTPException(status_code=400, detail="You can't disable your own account.")
    store.update_user(user_id, name=req.name, active=req.active)
    forget_sessions()
    return {"user": store.public_user(store.get_user(user_id))}


@router.post("/admin/users/{user_id}/reset-password")
def reset_password(user_id: str, admin: dict = Depends(require_admin)):
    user = _managed_user(user_id)
    if user["id"] == admin["id"]:
        raise HTTPException(
            status_code=400, detail="Change your own password from the account menu instead."
        )
    password = temporary_password()
    store.set_password(user_id, password, must_change_password=True)
    forget_sessions()
    return {"temporary_password": password}
