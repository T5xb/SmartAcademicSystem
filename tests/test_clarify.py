"""Clarifying questions before the ticket suggestion (no LLM or DB needed)."""

import asyncio
import json
from types import SimpleNamespace

from src import tickets
from src.citation import NO_ANSWER_SENTINEL
from src.clarify import (
    CLARIFY_MARK,
    MAX_CLARIFY_ATTEMPTS,
    TICKET_MARK,
    clarify_streak,
    is_vague,
    pending_question,
    unanswered_reply,
)
from src.workflow import DirectQueryWorkflow


class FakeTool:
    """Stands in for the RAG query tool: records queries, returns a fixed answer."""

    def __init__(self, answer=NO_ANSWER_SENTINEL):
        self.answer = answer
        self.queries = []

    async def acall(self, input):
        self.queries.append(input)
        return SimpleNamespace(content=self.answer, raw_output=SimpleNamespace(source_nodes=[]))


def chat(workflow, message, history=None):
    return asyncio.run(workflow.respond(message, history or []))


# ------------------------------------------------------------ detection


def test_vague_messages():
    for q in ["عندي مشكلة", "ممكن سؤال؟", "السلام عليكم عندي استفسار ضروري", "احد يعرف؟",
              "ساعدوني", "؟؟", "الجامعة", "عندي مشكلة بالتسجيل"]:
        assert is_vague(q), q


def test_clear_questions_are_not_vague():
    for q in ["كم نسبة الغياب؟", "تحويل", "ابي اعرف رؤية الجامعة", "عندي مشكلة بالحذف",
              "وش شروط التحويل من نظم لعلوم الحاسب؟", "ما هي رؤية الجامعة؟"]:
        assert not is_vague(q), q


# ------------------------------------------------------------ counting


def history_with(clarifications):
    h = [{"role": "user", "text": "عندي مشكلة"}]
    for i in range(clarifications):
        h.append({"role": "bot", "text": f"{CLARIFY_MARK} وضّح أكثر {i}"})
        h.append({"role": "user", "text": f"توضيح {i}"})
    return h[:-1] if clarifications else h


def test_streak_counts_only_the_latest_run_of_clarifications():
    assert clarify_streak([]) == 0
    assert clarify_streak(history_with(1)) == 1
    assert clarify_streak(history_with(2)) == 2
    reset = history_with(2) + [{"role": "user", "text": "x"},
                               {"role": "bot", "text": "الجواب الكامل\n\nالمصادر:\n[1] ملف"}]
    assert clarify_streak(reset) == 0


def test_greeting_before_the_mark_still_counts():
    h = [{"role": "user", "text": "السلام عليكم عندي مشكلة"},
         {"role": "bot", "text": f"وعليكم السلام ورحمة الله وبركاته 🌷\n\n{CLARIFY_MARK} وضّح"}]
    assert clarify_streak(h) == 1


def test_pending_question_joins_the_students_answers():
    h = [{"role": "user", "text": "عندي مشكلة بالتسجيل"},
         {"role": "bot", "text": f"{CLARIFY_MARK} وضّح"}]
    assert pending_question(h, "ما قدرت انزل مادة") == "عندي مشكلة بالتسجيل\nما قدرت انزل مادة"
    # No clarification pending: only the new message.
    assert pending_question([], "كم الغياب؟") == "كم الغياب؟"


def test_ticket_only_after_the_allowed_attempts():
    for n in range(MAX_CLARIFY_ATTEMPTS):
        assert CLARIFY_MARK in unanswered_reply("عندي مشكلة", history_with(n))
    out = unanswered_reply("عندي مشكلة", history_with(MAX_CLARIFY_ATTEMPTS))
    assert TICKET_MARK in out and "تذكرة" in out
    assert "@" not in out  # no longer points straight at the e-mail


# ------------------------------------------------------------ whole flow


def test_vague_question_is_clarified_without_a_search():
    tool = FakeTool()
    reply, ticket = chat(DirectQueryWorkflow(tool), "عندي مشكلة")
    assert CLARIFY_MARK in reply and ticket is None
    assert tool.queries == []  # saved a model call


def test_unanswered_question_clarifies_then_suggests_a_ticket():
    wf = DirectQueryWorkflow(FakeTool())  # the documents never have the answer
    history = []
    for msg in ["وش نظام المواقف في الكلية؟", "اقصد مواقف السيارات للطلاب", "وين اوقف سيارتي"]:
        reply, ticket = chat(wf, msg, history)
        history += [{"role": "user", "text": msg}, {"role": "bot", "text": reply}]
    replies = [m["text"] for m in history if m["role"] == "bot"]
    assert [CLARIFY_MARK in r for r in replies] == [True, True, False]
    assert TICKET_MARK in replies[-1]
    assert ticket and ticket["status"] == "open"
    assert "مواقف السيارات" in ticket["summary"]
    assert ticket["transcript"][-1] == {"role": "user", "text": "وين اوقف سيارتي"}


def test_clarified_question_is_searched_with_the_earlier_message():
    tool = FakeTool(answer="تقدر تضيف المقرر في فترة التسجيل الإلحاقي.")
    h = [{"role": "user", "text": "عندي مشكلة بالتسجيل"},
         {"role": "bot", "text": f"{CLARIFY_MARK} وضّح"}]
    reply, ticket = chat(DirectQueryWorkflow(tool), "ما قدرت انزل مادة", h)
    assert "الإلحاقي" in reply and ticket is None
    assert tool.queries[0].startswith("عندي مشكلة بالتسجيل\nما قدرت انزل مادة")


def test_answered_question_is_unchanged():
    tool = FakeTool(answer="الغياب المسموح 25%.")
    reply, ticket = chat(DirectQueryWorkflow(tool), "كم نسبة الغياب؟")
    assert reply == "الغياب المسموح 25%." and ticket is None


# ------------------------------------------------------------ tickets hook


def test_ticket_masks_ids_and_emails():
    t = tickets.build_ticket("رقمي 441012345 وايميلي a.b@imamu.edu.sa",
                             [{"role": "user", "text": "جوالي 0551234567"}])
    assert "441012345" not in t["summary"] and "@" not in t["summary"]
    assert "0551234567" not in t["transcript"][0]["text"]


def test_create_ticket_is_off_by_default_and_writes_jsonl_when_on(tmp_path, monkeypatch):
    monkeypatch.setattr(tickets, "TICKETS_FILE", "")
    assert not tickets.tickets_enabled()
    path = tmp_path / "tickets.jsonl"
    monkeypatch.setattr(tickets, "TICKETS_FILE", str(path))
    t = tickets.create_ticket(tickets.build_ticket("سؤال", []))
    saved = json.loads(path.read_text(encoding="utf-8").strip())
    assert saved["id"] == t["id"] and saved["status"] == "open"


# ------------------------------------------------------------ API


def test_chat_api_passes_history_and_returns_ticket(monkeypatch):
    from fastapi.testclient import TestClient

    import fastapi_app

    monkeypatch.setattr(fastapi_app, "workflow", DirectQueryWorkflow(FakeTool()))
    client = TestClient(fastapi_app.app)  # no lifespan: the real index isn't loaded
    history = history_with(MAX_CLARIFY_ATTEMPTS)
    r = client.post("/api/chat", json={"message": "ما زالت المشكلة", "history": history})
    assert r.status_code == 200
    body = r.json()
    assert TICKET_MARK in body["response"] and body["ticket"]["status"] == "open"

    # The dashboard hook is off until TICKETS_FILE is set.
    monkeypatch.setattr(tickets, "TICKETS_FILE", "")
    r = client.post("/api/tickets", json={"summary": "سؤال", "transcript": history})
    assert r.status_code == 503
