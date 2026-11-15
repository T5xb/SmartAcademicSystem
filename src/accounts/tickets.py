"""
Advising tickets: a student opens one, then student and advisors chat in it
until an advisor closes it.

Status flow:  new  -> (an advisor replies) ->  in_progress  -> (closed by an advisor) ->  closed
An advisor can reopen a closed ticket. Every advisor and admin sees every
ticket; a student sees only their own. Tickets and their messages are kept
in the accounts database (tables sas_tickets and sas_ticket_messages).
"""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .api import student_detail
from .db import get_engine
from .deps import require_advisor, require_roles
from .store import _retry, _row, _rows

STATUSES = ("new", "in_progress", "closed")
FIRST_NUMBER = 4000          # the first ticket is TK-4001
MAX_OPEN_PER_STUDENT = 10    # open (not closed) tickets a student may have at once
MAX_MESSAGES = 500           # per ticket
MAX_BODY = 2000
RECENT_PER_STATUS = 10       # tickets per column on the advisors' dashboard

router = APIRouter(prefix="/api")
require_student = require_roles("student")


# ------------------------------------------------------------------ models


class NewTicket(BaseModel):
    # The student's name and university ID come from their account, so the
    # form doesn't ask for them (sent values are ignored).
    title: str = Field(min_length=3, max_length=150)
    # The problem in the student's words, e.g. the question the chatbot couldn't answer.
    message: str = Field(default="", max_length=MAX_BODY)

    @field_validator("title", "message")
    @classmethod
    def tidy(cls, value: str) -> str:
        return value.strip()


class NewMessage(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY)
    # Advisors only: send the reply and mark the ticket resolved in one step.
    close: bool = False


# ------------------------------------------------------------------ store


def now_iso() -> str:
    # Microseconds, unlike db.now_iso(): "replied after the student last
    # looked" and message order must hold within the same second too.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _code(number: int) -> str:
    return f"TK-{number}"


def _ticket(row) -> dict | None:
    if row is None:
        return None
    t = dict(row._mapping)
    t["code"] = _code(t["number"])
    # A staff reply the student hasn't opened yet.
    t["unread"] = bool(
        t.get("last_staff_reply_at")
        and (not t.get("student_seen_at") or t["last_staff_reply_at"] > t["student_seen_at"])
    )
    return t


def _message(row) -> dict:
    return dict(row._mapping)


def _new_id() -> str:
    return secrets.token_hex(8)


def get_ticket(ticket_id: str) -> dict | None:
    return _ticket(_row("SELECT * FROM sas_tickets WHERE id = :id", {"id": ticket_id}))


def messages(ticket_id: str) -> list[dict]:
    return [
        _message(r) for r in _rows(
            "SELECT * FROM sas_ticket_messages WHERE ticket_id = :id ORDER BY created_at, id",
            {"id": ticket_id},
        )
    ]


def _insert_message(conn, ticket_id: str, user: dict, body: str, at: str) -> dict:
    message = {
        "id": _new_id(),
        "ticket_id": ticket_id,
        "sender_id": user["id"],
        "sender_role": user["role"],
        "sender_name": user["name"],
        "body": body,
        "created_at": at,
    }
    conn.execute(
        text(
            "INSERT INTO sas_ticket_messages (id, ticket_id, sender_id, sender_role, sender_name, body, created_at)"
            " VALUES (:id, :ticket_id, :sender_id, :sender_role, :sender_name, :body, :created_at)"
        ),
        message,
    )
    return message


@_retry
def create_ticket(student: dict, req: NewTicket) -> dict:
    # The number is the next free one; two students opening a ticket in the
    # same instant collide on the UNIQUE number, so that case tries again.
    for _ in range(5):
        at = now_iso()
        ticket_id = _new_id()
        try:
            with get_engine().begin() as conn:
                number = conn.execute(
                    text("SELECT COALESCE(MAX(number), :first) + 1 FROM sas_tickets"),
                    {"first": FIRST_NUMBER},
                ).scalar_one()
                conn.execute(
                    text(
                        "INSERT INTO sas_tickets (id, number, student_id, full_name, university_id, title,"
                        " status, created_at, updated_at, student_seen_at)"
                        " VALUES (:id, :number, :student_id, :full_name, :university_id, :title,"
                        " 'new', :at, :at, :at)"
                    ),
                    {
                        "id": ticket_id, "number": number, "student_id": student["id"],
                        "full_name": student["name"], "university_id": student["username"],
                        "title": req.title, "at": at,
                    },
                )
                if req.message:
                    _insert_message(conn, ticket_id, student, req.message, at)
            return get_ticket(ticket_id)
        except IntegrityError:
            continue
    raise HTTPException(status_code=503, detail="Couldn't open the ticket right now. Please try again.")


@_retry
def add_message(ticket: dict, user: dict, body: str) -> dict:
    at = now_iso()
    staff = user["role"] != "student"
    with get_engine().begin() as conn:
        message = _insert_message(conn, ticket["id"], user, body, at)
        if staff:
            # The first advisor reply moves a new ticket to "in progress".
            conn.execute(
                text(
                    "UPDATE sas_tickets SET updated_at = :at, last_staff_reply_at = :at,"
                    " status = CASE WHEN status = 'new' THEN 'in_progress' ELSE status END"
                    " WHERE id = :id"
                ),
                {"at": at, "id": ticket["id"]},
            )
        else:
            conn.execute(
                text("UPDATE sas_tickets SET updated_at = :at, student_seen_at = :at WHERE id = :id"),
                {"at": at, "id": ticket["id"]},
            )
    return message


@_retry
def set_status(ticket_id: str, status: str, user: dict) -> None:
    at = now_iso()
    with get_engine().begin() as conn:
        if status == "closed":
            conn.execute(
                text(
                    "UPDATE sas_tickets SET status = 'closed', closed_at = :at, closed_by = :by,"
                    " updated_at = :at WHERE id = :id"
                ),
                {"at": at, "by": user["name"], "id": ticket_id},
            )
        else:
            conn.execute(
                text(
                    "UPDATE sas_tickets SET status = :status, closed_at = NULL, closed_by = NULL,"
                    " updated_at = :at WHERE id = :id"
                ),
                {"status": status, "at": at, "id": ticket_id},
            )


@_retry
def mark_seen(ticket_id: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE sas_tickets SET student_seen_at = :at WHERE id = :id"),
            {"at": now_iso(), "id": ticket_id},
        )


def message_count(ticket_id: str) -> int:
    row = _row("SELECT COUNT(*) AS n FROM sas_ticket_messages WHERE ticket_id = :id", {"id": ticket_id})
    return int(row.n) if row else 0


def _start_of_today_utc() -> str:
    """Midnight of today in the server's own time zone, as a UTC timestamp."""
    midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc).isoformat(timespec="seconds")


def staff_counts() -> dict:
    rows = _rows("SELECT status, COUNT(*) AS n FROM sas_tickets GROUP BY status")
    counts = {status: 0 for status in STATUSES}
    for r in rows:
        counts[r.status] = int(r.n)
    today = _row(
        "SELECT COUNT(*) AS n FROM sas_tickets WHERE created_at >= :since",
        {"since": _start_of_today_utc()},
    )
    return {"all": sum(counts.values()), **counts, "new_today": int(today.n) if today else 0}


def search_tickets(status: str | None = None, q: str = "", limit: int | None = None) -> list[dict]:
    query = "SELECT * FROM sas_tickets WHERE 1 = 1"
    params: dict = {}
    if status:
        query += " AND status = :status"
        params["status"] = status
    q = q.strip()
    if q:
        number = q.upper().removeprefix("TK-").removeprefix("#")
        query += (
            " AND (LOWER(title) LIKE :like OR LOWER(full_name) LIKE :like"
            " OR university_id LIKE :like OR CAST(number AS TEXT) = :number)"
        )
        params["like"] = f"%{q.lower()}%"
        params["number"] = number
    query += " ORDER BY updated_at DESC, number DESC"
    if limit:
        query += " LIMIT :limit"
        params["limit"] = limit
    return [_ticket(r) for r in _rows(query, params)]


def student_tickets(student_id: str) -> list[dict]:
    return [
        _ticket(r) for r in _rows(
            "SELECT * FROM sas_tickets WHERE student_id = :id ORDER BY updated_at DESC, number DESC",
            {"id": student_id},
        )
    ]


# ------------------------------------------------------------------ helpers


def _found(ticket_id: str) -> dict:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


def _own(ticket_id: str, student: dict) -> dict:
    ticket = get_ticket(ticket_id)
    # Someone else's ticket answers like a missing one: no hint it exists.
    if ticket is None or ticket["student_id"] != student["id"]:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


def _post(ticket: dict, user: dict, body: str) -> dict:
    body = body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Write a message first.")
    if ticket["status"] == "closed":
        raise HTTPException(status_code=409, detail="This ticket is closed, so no more messages can be added.")
    if message_count(ticket["id"]) >= MAX_MESSAGES:
        raise HTTPException(status_code=409, detail="This ticket has reached its message limit. Please open a new one.")
    return add_message(ticket, user, body)


def _with_messages(ticket: dict) -> dict:
    return {"ticket": ticket, "messages": messages(ticket["id"])}


# ------------------------------------------------------------------ student routes


@router.get("/tickets")
def my_tickets(student: dict = Depends(require_student)):
    tickets = student_tickets(student["id"])
    return {"tickets": tickets, "unread": sum(t["unread"] for t in tickets)}


@router.post("/tickets", status_code=201)
def open_ticket(req: NewTicket, student: dict = Depends(require_student)):
    still_open = [t for t in student_tickets(student["id"]) if t["status"] != "closed"]
    if len(still_open) >= MAX_OPEN_PER_STUDENT:
        raise HTTPException(
            status_code=429,
            detail=f"You already have {MAX_OPEN_PER_STUDENT} open tickets. Please wait for advising to close one first.",
        )
    return _with_messages(create_ticket(student, req))


@router.get("/tickets/{ticket_id}")
def my_ticket(ticket_id: str, student: dict = Depends(require_student)):
    ticket = _own(ticket_id, student)
    if ticket["unread"]:
        mark_seen(ticket_id)
        ticket = get_ticket(ticket_id)
    return _with_messages(ticket)


@router.post("/tickets/{ticket_id}/messages", status_code=201)
def student_message(ticket_id: str, req: NewMessage, student: dict = Depends(require_student)):
    ticket = _own(ticket_id, student)
    return {"message": _post(ticket, student, req.body), "ticket": get_ticket(ticket_id)}


# ------------------------------------------------------------------ advisor routes


@router.get("/advisor/tickets")
def staff_tickets(status: str | None = None, q: str = "", _: dict = Depends(require_advisor)):
    if status and status not in STATUSES:
        raise HTTPException(status_code=422, detail="Unknown ticket status.")
    return {"tickets": search_tickets(status, q), "counts": staff_counts()}


@router.get("/advisor/tickets/overview")
def staff_overview(_: dict = Depends(require_advisor)):
    """The dashboard: counts, and the latest tickets of each status."""
    return {
        "counts": staff_counts(),
        "recent": {s: search_tickets(s, limit=RECENT_PER_STATUS) for s in STATUSES},
    }


@router.get("/advisor/tickets/{ticket_id}")
def staff_ticket(ticket_id: str, _: dict = Depends(require_advisor)):
    ticket = _found(ticket_id)
    # The student's academic profile is shown under the conversation.
    return {**_with_messages(ticket), "student": student_detail(ticket["student_id"])}


@router.post("/advisor/tickets/{ticket_id}/messages", status_code=201)
def staff_message(ticket_id: str, req: NewMessage, staff: dict = Depends(require_advisor)):
    ticket = _found(ticket_id)
    message = _post(ticket, staff, req.body)
    if req.close:
        set_status(ticket_id, "closed", staff)
    return {"message": message, "ticket": get_ticket(ticket_id)}


@router.post("/advisor/tickets/{ticket_id}/close")
def close_ticket(ticket_id: str, staff: dict = Depends(require_advisor)):
    ticket = _found(ticket_id)
    if ticket["status"] != "closed":
        set_status(ticket_id, "closed", staff)
    return {"ticket": get_ticket(ticket_id)}


@router.post("/advisor/tickets/{ticket_id}/reopen")
def reopen_ticket(ticket_id: str, staff: dict = Depends(require_advisor)):
    ticket = _found(ticket_id)
    if ticket["status"] == "closed":
        set_status(ticket_id, "in_progress" if ticket["last_staff_reply_at"] else "new", staff)
    return {"ticket": get_ticket(ticket_id)}
