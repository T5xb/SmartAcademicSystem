"""
Tickets to academic advising: the hook for the advisors' dashboard.

When the bot can't answer after its clarifying questions, /api/chat returns
a ticket draft next to the reply (`ticket`). A future ticket page sends it
(after the student confirms or edits it) to POST /api/tickets, which calls
create_ticket() below. The advisors' dashboard then reads the saved tickets.

For now create_ticket() only appends to a local JSON-lines file, and only
when TICKETS_FILE is set in src/.env (off by default). To plug in the real
dashboard, replace the body of create_ticket() with a write to its database
or API; the ticket shape stays the same.

Ticket shape (JSON):
    {
      "id":         "t_20261028_174512_ab12cd",
      "created_at": "2026-10-28T17:45:12+00:00",
      "status":     "open",
      "summary":    "the student's question, as they wrote it",
      "transcript": [{"role": "user" | "bot", "text": "..."}],   # last messages
      "contact":    ""      # filled by the ticket page later (e.g. student email)
    }

No personal data is added by the server: no name, no ID, no IP. Long digit
runs (student IDs, phone numbers) and e-mail addresses in the text are
masked, since the chat page sends whatever the student typed.
"""

import json
import os
import re
import secrets
from datetime import datetime, timezone

TICKETS_FILE = os.getenv("TICKETS_FILE", "").strip()

MAX_TRANSCRIPT = 10
MAX_TEXT = 1500

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LONG_DIGITS_RE = re.compile(r"(?:\d[\s-]?){6,}")


def scrub(text: str) -> str:
    """Mask e-mails and long numbers (IDs, phones) and cap the length."""
    text = _EMAIL_RE.sub("[بريد]", text or "")
    text = _LONG_DIGITS_RE.sub("[رقم] ", text)
    return text.strip()[:MAX_TEXT]


def build_ticket(summary: str, transcript: list[dict]) -> dict:
    """A ticket draft from the student's question and the recent messages."""
    now = datetime.now(timezone.utc)
    return {
        "id": f"t_{now:%Y%m%d_%H%M%S}_{secrets.token_hex(3)}",
        "created_at": now.isoformat(timespec="seconds"),
        "status": "open",
        "summary": scrub(summary),
        "transcript": [
            {"role": m["role"], "text": scrub(m["text"])}
            for m in transcript[-MAX_TRANSCRIPT:]
            if m.get("role") in ("user", "bot") and (m.get("text") or "").strip()
        ],
        "contact": "",
    }


def tickets_enabled() -> bool:
    return bool(TICKETS_FILE)


def create_ticket(ticket: dict) -> dict:
    """
    Save a ticket for the advisors. Currently: one JSON line in TICKETS_FILE.
    Raises RuntimeError when tickets are not enabled.
    """
    if not tickets_enabled():
        raise RuntimeError("Tickets are not enabled (set TICKETS_FILE in src/.env).")
    folder = os.path.dirname(TICKETS_FILE)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(TICKETS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(ticket, ensure_ascii=False) + "\n")
    return ticket
