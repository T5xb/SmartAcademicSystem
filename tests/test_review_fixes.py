"""Regression tests for the fixes from the project review (no LLM or DB needed)."""

from datetime import date

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from src import generate, index, quick_answers
from src.quick_answers import date_reply
from src.student_style import formal_terms

TODAY = date(2026, 11, 10)


# ------------------------------------------------------------ glossary


def test_glossary_does_not_match_inside_other_words():
    assert "مرتبة الشرف" not in formal_terms("مين المشرف على المشروع")
    assert "شعب المقررات والجدول الدراسي" not in formal_terms("متى يبدأ شهر شعبان")


def test_glossary_still_matches_the_real_words():
    assert "مرتبة الشرف" in formal_terms("كم لازم معدلي عشان اخذ مرتبة الشرف؟")
    assert "مرتبة الشرف" in formal_terms("وش شروط الشرف")
    for question in ("وين القى قروبات الشعب؟", "ابي اغير شعبتي", "شعبه الدكتور مقفله"):
        assert "شعب المقررات والجدول الدراسي" in formal_terms(question)


# ------------------------------------------------------------ calendar


def test_semester_is_read_from_the_semester_words_only():
    # "ثانية" here is "another university", not the second semester.
    other_university = date_reply("متى التحويل الخارجي من جامعة ثانية", TODAY)
    plain = date_reply("متى التحويل الخارجي", TODAY)
    assert other_university == plain
    assert "17/01/2027" in date_reply("متى يبدأ الترم الثاني؟", TODAY)
    assert "17/01/2027" in date_reply("متى تبدأ الدراسة ثاني ترم", TODAY)
    first = date_reply("متى يبدأ الفاينل للترم الاول؟", TODAY)
    assert "الفصل الدراسي الأول" in first


def test_missing_calendar_file_falls_back_to_rag(monkeypatch):
    def missing():
        raise FileNotFoundError("no calendar")

    monkeypatch.setattr(quick_answers, "_calendar", missing)
    assert date_reply("متى يبدأ الحذف؟", TODAY) is None


# ------------------------------------------------------------ index


class _FakeEngine:
    def __init__(self, error):
        self.error = error

    def connect(self):
        raise self.error

    def dispose(self):
        pass


def _use_engine(monkeypatch, error):
    monkeypatch.setattr(index, "sqlalchemy_urls", lambda: ("postgresql://x", "postgresql://x"))
    monkeypatch.setattr(index, "create_engine", lambda url: _FakeEngine(error))


def test_missing_table_counts_as_empty_index(monkeypatch):
    _use_engine(monkeypatch, ProgrammingError("select", {}, Exception("relation does not exist")))
    assert index.count_indexed_chunks() == 0


def test_database_failure_is_not_reported_as_empty_index(monkeypatch):
    _use_engine(monkeypatch, OperationalError("select", {}, Exception("password authentication failed")))
    with pytest.raises(OperationalError):
        index.count_indexed_chunks()


# ------------------------------------------------------------ generate


class _FakeEmbedding:
    def __init__(self, vector=None, error=None):
        self.vector, self.error = vector, error

    def get_text_embedding(self, text):
        if self.error:
            raise self.error
        return self.vector


def test_embedding_check_stops_before_the_table_is_dropped(monkeypatch):
    from llama_index.core import Settings

    monkeypatch.setattr(Settings, "_embed_model", _FakeEmbedding(error=ConnectionError("down")))
    with pytest.raises(RuntimeError, match="left unchanged"):
        generate._check_embedding(1024)

    monkeypatch.setattr(Settings, "_embed_model", _FakeEmbedding(vector=[0.0] * 768))
    with pytest.raises(RuntimeError, match="768"):
        generate._check_embedding(1024)

    monkeypatch.setattr(Settings, "_embed_model", _FakeEmbedding(vector=[0.0] * 1024))
    generate._check_embedding(1024)


# ------------------------------------------------------------ rate limit


def test_chat_rate_limit(monkeypatch, sign_in):
    import fastapi_app
    from src.workflow import DirectQueryWorkflow
    from tests.test_clarify import FakeTool

    monkeypatch.setattr(fastapi_app, "workflow", DirectQueryWorkflow(FakeTool()))
    monkeypatch.setattr(fastapi_app, "CHAT_RATE_LIMIT", 2)
    fastapi_app._chat_hits.clear()
    client = sign_in("441000001")

    ask = lambda headers=None: client.post(  # noqa: E731
        "/api/chat", json={"message": "السلام عليكم"}, headers=headers or {}
    ).status_code
    assert [ask(), ask(), ask()] == [200, 200, 429]
    # Another visitor behind the public tunnel is counted on their own.
    assert ask({"X-Forwarded-For": "203.0.113.7"}) == 200

    monkeypatch.setattr(fastapi_app, "CHAT_RATE_LIMIT", 0)
    assert ask() == 200
    fastapi_app._chat_hits.clear()
