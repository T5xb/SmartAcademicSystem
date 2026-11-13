"""
RAGAS evaluation suite for the Smart Academic System (GP2, Group M3).

Every test case is scored with RAGAS metrics only:
  * RAG answers (retrieval + generation): Faithfulness, AnswerRelevancy,
    ContextPrecision, ContextRecall, AnswerCorrectness (LLM judge + embeddings).
  * Deterministic tasks (routing, scheduler, accounts, API, GUI pages): the
    observed behaviour is written as a short text and compared with the
    expected text by RAGAS's ExactMatch / StringPresence metrics.

The suite runs against the real system: the FastAPI server is started inside
this process (same lifespan as Start-API.bat), the index is the live Supabase
pgvector table, embeddings come from the local Ollama, and answers come from
the hosted LLM. Only the accounts database is a throwaway SQLite file, so the
tests never touch real accounts.

Run (from the project root):
    .venv/Scripts/python.exe -m evaluation.ragas_suite
    .venv/Scripts/python.exe -m evaluation.ragas_suite --only TC-11 TC-43

Results: output/ragas/results_<stamp>.json, report_<stamp>.md, run_<stamp>.log
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
import platform
import re
import shutil
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Awaitable, Callable

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

# Arabic and emoji in the console: Windows defaults to cp1256 and crashes on them.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv("src/.env")

# A throwaway accounts database and backup folder, set before the app is imported.
TMP_DIR = tempfile.mkdtemp(prefix="sas_ragas_")
os.environ["ACCOUNTS_DB_URL"] = f"sqlite:///{os.path.join(TMP_DIR, 'accounts.db').replace(os.sep, '/')}"
os.environ["DOCS_BACKUP_DIR"] = os.path.join(TMP_DIR, "backup")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import warnings  # noqa: E402

warnings.filterwarnings("ignore")

from openai import AsyncOpenAI  # noqa: E402
from ragas.cache import DiskCacheBackend  # noqa: E402
from ragas.embeddings import embedding_factory  # noqa: E402
from ragas.llms import llm_factory  # noqa: E402
from ragas.metrics.collections import (  # noqa: E402
    AnswerCorrectness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    ExactMatch,
    Faithfulness,
    StringPresence,
)

from evaluation.golden_set import GOLDEN  # noqa: E402

OUT_DIR = os.path.join(PROJECT_DIR, "output", "ragas")
os.makedirs(OUT_DIR, exist_ok=True)
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_PATH = os.path.join(OUT_DIR, f"run_{STAMP}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
for noisy in ("httpx", "httpcore", "openai", "instructor", "uvicorn.access", "ragas"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("ragas-suite")

# Pass thresholds for the LLM-judged RAG metrics (fixed before the first run).
RAG_THRESHOLDS = {
    "faithfulness": 0.70,
    "answer_relevancy": 0.70,
    "context_precision": 0.50,
    "context_recall": 0.70,
    "answer_correctness": 0.50,
    "citation_present": 1.0,
}
# gpt-oss-120b ran out of its free 200K tokens/day during the first runs; the
# 20B model has its own quota. Judge answers are cached on disk between runs.
JUDGE_MODEL = os.getenv("RAGAS_JUDGE_MODEL", "openai/gpt-oss-20b")


def _free_port() -> int:
    """A port nothing listens on (a previous run may still hold the old one)."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = int(os.getenv("RAGAS_PORT", "0")) or _free_port()

# ------------------------------------------------------------------ model


@dataclass
class Outcome:
    input: str
    expected: str
    actual: str
    scores: dict
    thresholds: dict
    route: str = ""
    contexts: list = field(default_factory=list)


@dataclass
class Result:
    id: str
    task: str
    technique: str
    components: str
    input: str = ""
    expected: str = ""
    actual: str = ""
    scores: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)
    status: str = "ERROR"
    error: str | None = None
    route: str = ""
    seconds: float = 0.0
    contexts: list = field(default_factory=list)


CASES: list[tuple[str, str, str, str, Callable[["Ctx"], Awaitable[Outcome]]]] = []


def case(cid: str, task: str, technique: str, components: str):
    def register(fn):
        CASES.append((cid, task, technique, components, fn))
        return fn

    return register


# ----------------------------------------------------- RAGAS string checks

_EXACT = ExactMatch()
_PRESENT = StringPresence()


def render(facts: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in facts.items())


async def facts_check(input_text: str, observed: dict, expected: dict, route: str = "") -> Outcome:
    """Observed behaviour vs expected behaviour, scored by RAGAS ExactMatch."""
    actual, reference = render(observed), render(expected)
    score = (await _EXACT.ascore(reference=reference, response=actual)).value
    return Outcome(input_text, reference, actual, {"exact_match": score}, {"exact_match": 1.0}, route)


async def presence_check(input_text: str, response: str, must_contain: list[str], route: str = "") -> Outcome:
    """Every expected phrase must appear in the response (RAGAS StringPresence)."""
    scores = {}
    for i, phrase in enumerate(must_contain, 1):
        scores[f"string_presence_{i}"] = (await _PRESENT.ascore(reference=phrase, response=response)).value
    return Outcome(
        input_text, " + ".join(f"«{p}»" for p in must_contain), response[:600],
        scores, {k: 1.0 for k in scores}, route,
    )


# ------------------------------------------------------------------ context


class RecordingTool:
    """Wraps the chatbot's query tool to keep the retrieved chunks for RAGAS."""

    def __init__(self, tool):
        self.tool = tool
        self.last = None
        self.metadata = getattr(tool, "metadata", None)

    async def acall(self, *args, **kwargs):
        self.last = None
        out = await self.tool.acall(*args, **kwargs)
        self.last = out
        return out


class Ctx:
    def __init__(self):
        self.base = f"http://127.0.0.1:{PORT}"
        self.password = ""
        self.clients: dict = {}
        self.app_module = None
        self.workflow = None
        self.recorder: RecordingTool | None = None
        api_base, api_key = os.getenv("LLM_API_BASE"), os.getenv("LLM_API_KEY")
        self.judge = llm_factory(
            JUDGE_MODEL,
            client=AsyncOpenAI(base_url=api_base, api_key=api_key, max_retries=8, timeout=180),
            # RAGAS's default max_tokens=1024 is used up by gpt-oss's hidden
            # reasoning before the JSON verdict is written (json_validate_failed).
            max_tokens=8192, reasoning_effort="low",
            cache=DiskCacheBackend(os.path.join(OUT_DIR, "judge_cache")),
        )
        self.embeddings = embedding_factory(
            "openai", model=os.getenv("EMBEDDING_MODEL", "bge-m3"),
            client=AsyncOpenAI(base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434") + "/v1",
                               api_key="ollama"),
        )
        self.metrics = {
            "faithfulness": Faithfulness(llm=self.judge),
            "answer_relevancy": AnswerRelevancy(llm=self.judge, embeddings=self.embeddings),
            "context_precision": ContextPrecision(llm=self.judge),
            "context_recall": ContextRecall(llm=self.judge),
            "answer_correctness": AnswerCorrectness(llm=self.judge, embeddings=self.embeddings),
        }

    async def client(self, username: str | None):
        """An HTTP client signed in as `username` (None = anonymous)."""
        import httpx

        key = username or "_anon"
        if key not in self.clients:
            c = httpx.AsyncClient(base_url=self.base, timeout=180)
            if username:
                r = await c.post("/api/auth/login", json={"username": username, "password": self.password})
                if r.status_code != 200:
                    raise RuntimeError(f"login {username} -> {r.status_code} {r.text}")
            self.clients[key] = c
        return self.clients[key]


# --------------------------------------------------------- RAG evaluation

_SOURCES_SPLIT = "\nالمصادر:"
_MARKER_RE = re.compile(r"\[\d+\]")


def answer_body(text: str) -> str:
    """The answer without the sources list and [n] markers, for the judge."""
    return _MARKER_RE.sub("", text.split(_SOURCES_SPLIT)[0]).strip()


async def rag_scores(ctx: Ctx, question: str, response: str, contexts: list[str], reference: str) -> dict:
    m = ctx.metrics
    body = answer_body(response)
    jobs = {
        "answer_relevancy": lambda: m["answer_relevancy"].ascore(user_input=question, response=body),
        "answer_correctness": lambda: m["answer_correctness"].ascore(
            user_input=question, response=body, reference=reference),
    }
    if contexts:
        jobs["faithfulness"] = lambda: m["faithfulness"].ascore(
            user_input=question, response=body, retrieved_contexts=contexts)
        jobs["context_precision"] = lambda: m["context_precision"].ascore(
            user_input=question, reference=reference, retrieved_contexts=contexts)
        jobs["context_recall"] = lambda: m["context_recall"].ascore(
            user_input=question, retrieved_contexts=contexts, reference=reference)
    scores = {}
    for name, job in jobs.items():
        try:
            scores[name] = round(float((await job()).value), 4)
        except Exception as e:  # one failing metric must not hide the others
            log.error("metric %s failed: %s", name, e)
            scores[name] = None
    if not contexts:
        # The question never reached retrieval (a shortcut route answered it).
        for name in ("faithfulness", "context_precision", "context_recall"):
            scores[name] = 0.0
    scores["citation_present"] = (await _PRESENT.ascore(reference="المصادر:", response=response)).value
    return scores


def _make_rag_case(item: dict):
    @case(item["id"], f"RAG answer: {item['topic']}", "Path testing (input question -> retrieval -> LLM -> cited answer)",
          "Retriever (bge-m3 + Supabase pgvector), LLM (Qwen3.8 27B), citation builder, workflow router")
    async def run(ctx: Ctx) -> Outcome:
        ctx.recorder.last = None
        response, _ = await ctx.workflow.respond(item["question"], [])
        out = ctx.recorder.last
        contexts, route = [], "quick_reply/shortcut"
        if out is not None:
            route = "rag"
            nodes = getattr(out.raw_output, "source_nodes", None) or []
            contexts = [n.node.get_content() for n in nodes]
        scores = await rag_scores(ctx, item["question"], response, contexts, item["reference"])
        return Outcome(item["question"], item["reference"], response, scores,
                       dict(RAG_THRESHOLDS), route, contexts)

    return run


for _item in GOLDEN:
    _make_rag_case(_item)


# ============================================================ TEST CASES

# ---------------------------------------------------- environment / runtime


@case("TC-01", "Runtime environment (hardware and services)", "Code coverage (critical requirement)",
      "Host machine, Python runtime, Ollama embedding server, hosted LLM API")
async def tc01(ctx: Ctx) -> Outcome:
    import httpx

    from src.generate import _check_embedding

    ollama = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    async with httpx.AsyncClient(timeout=30) as c:
        tags = (await c.get(f"{ollama}/api/tags")).json()
        models = (await c.get(os.getenv("LLM_API_BASE") + "/models",
                              headers={"Authorization": "Bearer " + os.getenv("LLM_API_KEY", "")})).json()
    try:
        _check_embedding(int(os.getenv("EMBED_DIM", "1024")))
        dim_ok = True
    except Exception:
        dim_ok = False
    observed = {
        "python>=3.11": sys.version_info >= (3, 11),
        "cpu_cores>=4": (os.cpu_count() or 0) >= 4,
        "ollama_has_bge-m3": any(m["name"].startswith("bge-m3") for m in tags.get("models", [])),
        "embedding_dim_matches_EMBED_DIM": dim_ok,
        "hosted_llm_model_available": os.getenv("LLM_MODEL") in {m["id"] for m in models.get("data", [])},
    }
    info = f"{platform.system()} {platform.release()}, Python {platform.python_version()}, {os.cpu_count()} cores"
    out = await facts_check(info, observed, {k: True for k in observed})
    return out


# ---------------------------------------------------------------- database


@case("TC-02", "Vector database connection and index", "Condition testing (connection-string rules)",
      "Supabase Postgres + pgvector (src/index.py)")
async def tc02(ctx: Ctx) -> Outcome:
    from src.index import count_indexed_chunks, sqlalchemy_urls

    sync_url, async_url = sqlalchemy_urls(
        "postgresql://u:p@aws-0-x.pooler.supabase.com:6543/postgres?sslmode=require")
    chunks = await asyncio.to_thread(count_indexed_chunks)
    observed = {
        "live_index_has_chunks": chunks > 0,
        "async_url_without_sslmode": "sslmode" not in async_url,
        "async_url_uses_asyncpg": async_url.startswith("postgresql+asyncpg://"),
        "sync_url_uses_psycopg2": sync_url.startswith("postgresql+psycopg2://"),
    }
    out = await facts_check(f"count_indexed_chunks() = {chunks}", observed, {k: True for k in observed})
    return out


@case("TC-03", "Accounts database: users, sessions, chats, profiles", "Path testing (create -> read -> update -> delete)",
      "SQLAlchemy accounts store (src/accounts/store.py, db.py)")
async def tc03(ctx: Ctx) -> Outcome:
    from datetime import timedelta

    from src.accounts import store

    def flow():
        u = store.create_user("ragas.user", "RAGAS User", "student", "pass-12345")
        try:
            store.create_user("RAGAS.user", "Dup", "student", "x-12345678")
            dup_rejected = False
        except store.UsernameTaken:
            dup_rejected = True
        token = store.create_session(u["id"], timedelta(minutes=5))
        session_ok = (store.session_user(token) or {}).get("id") == u["id"]
        store.delete_session(token)
        session_gone = store.session_user(token) is None
        store.save_chat(u["id"], "c1", {"title": "t", "messages": []})
        chat_saved = store.count_chats(u["id"]) == 1
        store.delete_chat(u["id"], "c1")
        profile = store.update_profile(u["id"], {"major": "علوم الحاسب"})
        return {
            "user_created": u["username"] == "ragas.user",
            "duplicate_username_rejected": dup_rejected,
            "session_lookup": session_ok,
            "session_deleted": session_gone,
            "chat_saved": chat_saved,
            "chat_deleted": store.count_chats(u["id"]) == 0,
            "profile_updated": profile.get("major") == "علوم الحاسب",
        }

    observed = await asyncio.to_thread(flow)
    return await facts_check("create_user / create_session / save_chat / update_profile", observed,
                             {k: True for k in observed})


@case("TC-04", "Password hashing and verification", "Condition testing (valid / wrong / malformed hash)",
      "src/accounts/security.py")
async def tc04(ctx: Ctx) -> Outcome:
    from src.accounts.security import hash_password, verify_password

    a, b = hash_password("test12345"), hash_password("test12345")
    observed = {
        "salted (two hashes differ)": a != b,
        "plain text not stored": "test12345" not in a,
        "right password accepted": verify_password("test12345", a),
        "wrong password rejected": not verify_password("test1234", a),
        "malformed hash rejected": not verify_password("test12345", "not-a-hash"),
    }
    return await facts_check("hash_password('test12345')", observed, {k: True for k in observed})


# ------------------------------------------------------------- ingestion


@case("TC-05", "Document ingestion (PDF loader and chunking settings)", "Code coverage (critical requirement)",
      "src/pdf_loader.py (PyMuPDF), src/settings.py chunking")
async def tc05(ctx: Ctx) -> Outcome:
    from llama_index.core import Settings

    from src.pdf_loader import load_pdf_as_documents

    path = "docs/imamu_web/admission_registration/GPA_calculation_and_academic_warnings_EN.pdf"
    docs = await asyncio.to_thread(load_pdf_as_documents, path)
    observed = {
        "pages_loaded>0": len(docs) > 0,
        "every_page_has_page_label": all(d.metadata.get("page_label") for d in docs),
        "every_page_has_file_name": all(d.metadata.get("file_name") for d in docs),
        "text_extracted": sum(len(d.text) for d in docs) > 500,
        "chunk_size=400": Settings.chunk_size == 400,
        "chunk_overlap=80": Settings.chunk_overlap == 80,
    }
    return await facts_check(path, observed, {k: True for k in observed})


# --------------------------------------------------------- RAG side tests


@case("TC-15", "Citation builder (code, not the LLM, writes sources)", "Condition testing (known id kept / unknown id dropped)",
      "src/citation.py format_citations")
async def tc15(ctx: Ctx) -> Outcome:
    from llama_index.core.schema import NodeWithScore, TextNode

    node = TextNode(id_="n1", text="...", metadata={"file_name": "docs/a/لائحة.md", "page_label": "3",
                                                    "article": "المادة الثانية"})
    from src.citation import format_citations

    out = format_citations("الجواب [citation:n1] ونص آخر [citation:fake-id].",
                           [NodeWithScore(node=node, score=0.9)])
    expected = "الجواب [1] ونص آخر .\n\nالمصادر:\n[1] لائحة.md — صفحة 3 — المادة الثانية"
    score = (await _EXACT.ascore(reference=expected, response=out)).value
    return Outcome("answer with one real and one unknown citation id", expected, out,
                   {"exact_match": score}, {"exact_match": 1.0})


@case("TC-16", "Out-of-scope question -> clarifying reply", "Path testing (retrieval -> LLM no-answer sentinel -> clarify)",
      "Workflow router, LLM sentinel, src/clarify.py")
async def tc16(ctx: Ctx) -> Outcome:
    q = "كم سعر تذكرة الطيران من الرياض إلى جدة؟"
    response, ticket = await ctx.workflow.respond(q, [])
    out = await presence_check(q, response, ["🤔|"], route="rag -> no answer -> clarify")
    out.scores["no_ticket_on_first_attempt"] = (await _EXACT.ascore(reference="None", response=str(ticket))).value
    out.thresholds["no_ticket_on_first_attempt"] = 1.0
    return out


# ------------------------------------------------------- routing branches


async def _route(ctx: Ctx, msg: str, history=None):
    ctx.recorder.last = None
    response, ticket = await ctx.workflow.respond(msg, history or [])
    return response, ticket, ("rag" if ctx.recorder.last is not None else "shortcut")


@case("TC-17", "Small talk: greeting", "Condition testing (small_talk_reply branch)",
      "Workflow router, src/student_style.py")
async def tc17(ctx: Ctx) -> Outcome:
    r, _, route = await _route(ctx, "السلام عليكم")
    out = await presence_check("السلام عليكم", r, ["وعليكم السلام", "مساعد الإرشاد الأكاديمي"], route)
    out.scores["no_llm_call"] = float(route == "shortcut")
    out.thresholds["no_llm_call"] = 1.0
    return out


@case("TC-18", "Small talk: thanks", "Condition testing (small_talk_reply branch)",
      "Workflow router, src/student_style.py")
async def tc18(ctx: Ctx) -> Outcome:
    r, _, route = await _route(ctx, "شكرا")
    out = await presence_check("شكرا", r, ["الله يعافيك"], route)
    out.scores["no_llm_call"] = float(route == "shortcut")
    out.thresholds["no_llm_call"] = 1.0
    return out


@case("TC-19", "Calendar date question", "Condition testing (date_reply branch)",
      "src/quick_answers.py date_reply + academic calendar file")
async def tc19(ctx: Ctx) -> Outcome:
    r, _, route = await _route(ctx, "متى ينتهي الحذف؟")
    return await presence_check("متى ينتهي الحذف؟", r, ["الانسحاب", "التقويم الدراسي"], route)


@case("TC-20", "Course prerequisite question", "Condition testing (prereq_reply branch)",
      "src/quick_answers.py prereq_reply + CS study plan")
async def tc20(ctx: Ctx) -> Outcome:
    r, _, route = await _route(ctx, "وش متطلب تراكيب البيانات؟")
    return await presence_check("وش متطلب تراكيب البيانات؟", r, ["عال 1241", "البرمجة الشيئية"], route)


@case("TC-21", "Contact e-mail question", "Condition testing (email_reply branch)",
      "src/contacts.py + college contact directory")
async def tc21(ctx: Ctx) -> Outcome:
    q = "ايميل الارشاد الاكاديمي علوم الحاسب"
    r, _, route = await _route(ctx, q)
    return await presence_check(q, r, ["cs.acadv@imamu.edu.sa"], route)


@case("TC-22", "Study-plan file request", "Condition testing (file_reply branch)",
      "src/quick_answers.py file_reply, /data static mount")
async def tc22(ctx: Ctx) -> Outcome:
    q = "ابي خطة علوم الحاسب"
    r, _, route = await _route(ctx, q)
    out = await presence_check(q, r, ["[📄 خطة علوم الحاسب](/data/"], route)
    import httpx

    link = re.search(r"\((/data/[^)]+)\)", r)
    async with httpx.AsyncClient(base_url=ctx.base) as c:
        status = (await c.get(link.group(1))).status_code if link else 0
    out.scores["linked_file_served_200"] = float(status == 200)
    out.thresholds["linked_file_served_200"] = 1.0
    return out


@case("TC-23", "Vague message -> first clarifying question", "Condition testing (is_vague branch, no retrieval)",
      "src/clarify.py is_vague / clarify_reply")
async def tc23(ctx: Ctx) -> Outcome:
    from src.clarify import is_vague

    r, ticket, route = await _route(ctx, "عندي مشكلة")
    observed = {
        "is_vague('عندي مشكلة')": is_vague("عندي مشكلة"),
        "is_vague('كم نسبة الغياب اللي تحرمني؟')": is_vague("كم نسبة الغياب اللي تحرمني؟"),
        "reply_is_clarifying": "🤔|" in r,
        "no_ticket": ticket is None,
        "retrieval_skipped": route == "shortcut",
    }
    expected = {k: True for k in observed}
    expected["is_vague('كم نسبة الغياب اللي تحرمني؟')"] = False
    out = await facts_check("عندي مشكلة", observed, expected, route)
    return out


@case("TC-24", "Clarify twice -> advising ticket draft", "Path testing (attempt 1 -> attempt 2 -> ticket)",
      "src/clarify.py, src/tickets.py, workflow router")
async def tc24(ctx: Ctx) -> Outcome:
    history = [
        {"role": "user", "text": "عندي مشكلة رقمي 441234567 وايميلي st@example.com"},
        {"role": "bot", "text": "🤔| ودي أساعدك، بس ما وضح لي سؤالك"},
        {"role": "user", "text": "ممكن سؤال"},
        {"role": "bot", "text": "🤔| للحين ما لقيت جواب واضح"},
    ]
    r, ticket, route = await _route(ctx, "ساعدوني", history)
    flat = json.dumps(ticket or {}, ensure_ascii=False)
    observed = {
        "reply_suggests_ticket": "🎫|" in r,
        "ticket_draft_returned": ticket is not None,
        "ticket_status_open": (ticket or {}).get("status") == "open",
        "student_id_masked": "441234567" not in flat,
        "email_masked": "st@example.com" not in flat,
    }
    return await facts_check("3rd vague message after two clarifying replies", observed,
                             {k: True for k in observed}, route)


@case("TC-25", "Dialect wording -> official terms (query expansion)", "Condition testing (formal_terms / bare keyword)",
      "src/student_style.py expand_query")
async def tc25(ctx: Ctx) -> Outcome:
    from src.student_style import expand_query

    q = "ابي احذف مادة"
    r = expand_query(q)
    return await presence_check(q, r, ["حذف مقرر دراسي", "أعطني معلومات عن"])


@case("TC-26", "Greeting + question in one message", "Path testing (greeting prefix + shortcut answer)",
      "src/student_style.py with_greeting, quick answers")
async def tc26(ctx: Ctx) -> Outcome:
    q = "السلام عليكم، وش متطلب تراكيب البيانات؟"
    r, _, route = await _route(ctx, q)
    out = await presence_check(q, r, ["وعليكم السلام", "عال 1241"], route)
    out.scores["greeting_first"] = float(r.startswith("وعليكم السلام"))
    out.thresholds["greeting_first"] = 1.0
    return out


# ------------------------------------------------------------- scheduling


def _clash_free(picks, by_code) -> bool:
    used = set()
    for p in picks:
        sec = next(s for s in by_code[p["code"]].available_sections if s.section_id == p["section"])
        slots = {t.index for t in sec.time_slots}
        if used & slots:
            return False
        used |= slots
    return True


@case("TC-27", "Course catalogue for the schedule page", "Code coverage (critical requirement)",
      "src/scheduling/service.py catalog, course_data.py")
async def tc27(ctx: Ctx) -> Outcome:
    from src.scheduling import service
    from src.scheduling.course_data import course_db

    cat = service.catalog()
    observed = {
        "courses": len(cat["courses"]),
        "max_electives": cat["max_electives"],
        "every_course_has_sections": all(c["sections"] for c in cat["courses"]),
    }
    return await facts_check("catalog()", observed,
                             {"courses": len(course_db), "max_electives": 3, "every_course_has_sections": True})


@case("TC-28", "Generate conflict-free schedules", "Path testing (selection -> validation -> CSP -> ranking)",
      "service.generate, validation.py, StudentCSPScheduler, evaluate_schedule")
async def tc28(ctx: Ctx) -> Outcome:
    from src.scheduling import service
    from src.scheduling.service import COURSE_BY_CODE

    codes = ["ريض 1112", "عال 1140", "احص 1011", "عال 1111"]
    res = service.generate(codes)
    scores = [s["score"] for s in res["schedules"]]
    observed = {
        "errors": len(res["errors"]),
        "schedules>0": len(res["schedules"]) > 0,
        "every_schedule_clash_free": all(_clash_free(s["picks"], COURSE_BY_CODE) for s in res["schedules"]),
        "every_course_placed": all(len(s["picks"]) == len(codes) for s in res["schedules"]),
        "ranked_best_first": scores == sorted(scores, reverse=True),
    }
    return await facts_check(", ".join(codes), observed,
                             {"errors": 0, "schedules>0": True, "every_schedule_clash_free": True,
                              "every_course_placed": True, "ranked_best_first": True})


@case("TC-29", "Credit-hour limit", "Condition testing (total > max_credit_hours)",
      "validation.check_credit_hours")
async def tc29(ctx: Ctx) -> Outcome:
    from src.scheduling import service

    over = service.generate(["ريض 1112", "ريض 1113", "عال 1140"], max_credit_hours=10)
    within = service.generate(["ريض 1112", "عال 1140"], max_credit_hours=10)
    observed = {"12h_with_max_10_rejected": bool(over["errors"]) and not over["schedules"],
                "8h_with_max_10_accepted": not within["errors"]}
    return await facts_check("max_credit_hours=10", observed, {k: True for k in observed})


@case("TC-30", "Elective-pool limit (max 3)", "Condition testing (electives > 3)",
      "validation.check_elective_pool_limit")
async def tc30(ctx: Ctx) -> Outcome:
    from src.scheduling import service

    four = service.generate(["عال 1424", "عال 1425", "عال 1426", "عال 1433"])
    three = service.generate(["عال 1424", "عال 1425", "عال 1426"])
    observed = {"4_electives_rejected": any("الاختياريات" in e for e in four["errors"]),
                "3_electives_accepted": not three["errors"]}
    return await facts_check("elective pool selection", observed, {k: True for k in observed})


@case("TC-31", "Prerequisite check after transcript import", "Condition testing (completed_courses None vs given)",
      "validation.check_prerequisites, service.generate")
async def tc31(ctx: Ctx) -> Outcome:
    from src.scheduling import service

    unknown_history = service.generate(["عال 1242"])
    missing = service.generate(["عال 1242"], completed_courses=[])
    met = service.generate(["عال 1242"], completed_courses=["عال 1140", "عال 1241"])
    observed = {"no_transcript_not_checked": not unknown_history["errors"],
                "missing_prereq_rejected": any("متطلبه السابق" in e for e in missing["errors"]),
                "prereq_met_accepted": not met["errors"]}
    return await facts_check("عال 1242 (needs عال 1241)", observed, {k: True for k in observed})


@case("TC-32", "Unknown course code / invalid lock", "Condition testing (input validation)",
      "service._target_courses, service.generate")
async def tc32(ctx: Ctx) -> Outcome:
    from src.scheduling import service

    def raises(fn) -> bool:
        try:
            fn()
            return False
        except service.ScheduleRequestError:
            return True

    observed = {"unknown_code_rejected": raises(lambda: service.generate(["XYZ 999"])),
                "lock_to_missing_section_rejected": raises(lambda: service.generate(["عال 1241"], locks={"عال 1241": "Z9"})),
                "empty_selection_returns_empty": service.generate([])["schedules"] == []}
    return await facts_check("invalid inputs", observed, {k: True for k in observed})


@case("TC-33", "Hard constraint H2: lecture clash", "Condition testing (_is_conflict)",
      "StudentCSPScheduler")
async def tc33(ctx: Ctx) -> Outcome:
    from src.scheduling import service

    res = service.generate(["ريض 1112", "عال 1100"])  # both only in slot ts1
    observed = {"schedules": len(res["schedules"]), "failure_reason_given": bool(res["failure_reason"])}
    return await facts_check("ريض 1112 + عال 1100 (same time slot)", observed,
                             {"schedules": 0, "failure_reason_given": True})


@case("TC-34", "Hard constraint H3: final-exam clash", "Condition testing (_exam_clash)",
      "StudentCSPScheduler, models.parse_exam_datetime")
async def tc34(ctx: Ctx) -> Outcome:
    from src.scheduling import service

    res = service.generate(["عال 1241", "عال 1242"])  # both finals 20-12-2026 08:00
    observed = {"schedules": len(res["schedules"]), "failure_reason_given": bool(res["failure_reason"])}
    return await facts_check("عال 1241 + عال 1242 (same final exam)", observed,
                             {"schedules": 0, "failure_reason_given": True})


@case("TC-35", "Hard constraints H6/H7: locked section and time window", "Condition testing (node consistency)",
      "StudentCSPScheduler._initial_domain")
async def tc35(ctx: Ctx) -> Outcome:
    from src.scheduling import service

    locked = service.generate(["عال 1241"], locks={"عال 1241": "C6"})
    window = service.generate(["عال 1100"], time_from="10:00", time_to="24:00")
    days = service.generate(["عال 1100", "عال 1111", "احص 1011"], min_days_off=4)
    observed = {
        "lock_respected": all(p["section"] == "C6" for s in locked["schedules"] for p in s["picks"])
        and bool(locked["schedules"]),
        "08:00_section_excluded_by_10:00_window": not window["schedules"],
        "min_4_days_off_unsatisfiable": not days["schedules"],
    }
    return await facts_check("locks / time window / days off", observed, {k: True for k in observed})


@case("TC-36", "Transcript import -> completed, eligible, suggested courses", "Path testing (PDF -> parser -> code mapping -> suggestions)",
      "transcript_parser.py (pdfplumber), code_mapping.py, service.import_transcript")
async def tc36(ctx: Ctx) -> Outcome:
    from src.scheduling import service

    pdf = make_transcript_pdf()
    res = service.import_transcript(io.BytesIO(pdf))
    observed = {
        "student_id": res["student"]["id"],
        "gpa": res["gpa"],
        "earned_hours": res["earned_hours"],
        "completed": ",".join(res["completed"]),
        "not_passed": ",".join(res["not_passed"]),
        "eligible_has_عال 1241": "عال 1241" in res["eligible"],
        "suggested_nonempty": bool(res["suggested"]),
    }
    expected = {"student_id": "400000000", "gpa": 4.0, "earned_hours": 7,
                "completed": "عال 1100,عال 1140", "not_passed": "MATH 101",
                "eligible_has_عال 1241": True, "suggested_nonempty": True}
    return await facts_check("synthetic transcript PDF (3 courses)", observed, expected)


def make_transcript_pdf() -> bytes:
    """A small text-based transcript in the university's table layout (synthetic data)."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 50
    for line in ["Name Test Student", "Student Id 400000000 Born In 2000",
                 "College Computer and Information Sciences", "Major Computer Science"]:
        page.insert_text((40, y), line, fontsize=10)
        y += 16
    rows = [
        ["Course Code", "Course Title", "", "C.Hours", "Q Points", "Grade"],
        ["CS 150", "Intro to Computer Programming", "", "4", "16", "A"],
        ["CS 114", "Discrete structures 1", "", "3", "12", "B+"],
        ["MATH 101", "Calculus 1", "", "0", "0", "W"],
        ["Hours", "Registered", "Passed", "Earned", "Q Points", "GPA"],
        ["Accumulative", "7", "7", "7", "28", "4.00"],
    ]
    widths = [80, 200, 40, 60, 60, 60]
    top, h = y + 10, 20
    for r, row in enumerate(rows):
        x = 40
        for c, text in enumerate(row):
            rect = fitz.Rect(x, top + r * h, x + widths[c], top + (r + 1) * h)
            page.draw_rect(rect, color=(0, 0, 0), width=0.7)
            if text:
                page.insert_text((x + 3, top + r * h + 14), text, fontsize=8)
            x += widths[c]
    data = doc.tobytes()
    doc.close()
    return data


@case("TC-37", "Transcript code mapping (old/new English codes -> plan codes)", "Condition testing (mapped / unmapped)",
      "src/scheduling/code_mapping.py")
async def tc37(ctx: Ctx) -> Outcome:
    from src.scheduling.code_mapping import map_transcript_codes

    mapped, unmapped = map_transcript_codes({"CS 252", "CS 1242", "CS 1141", "QUR 1001"})
    return await facts_check("{CS 252, CS 1242, CS 1141, QUR 1001}",
                             {"mapped": ",".join(sorted(mapped)), "unmapped": ",".join(sorted(unmapped))},
                             {"mapped": "عال 1241,عال 1242", "unmapped": "QUR 1001"})


# ------------------------------------------------------ API / integration

STUDENT, STUDENT_2, ADVISOR, ADMIN = "441000001", "441000002", "advisor", "admin"


@case("TC-38", "Server health and start-up", "Code coverage (critical requirement)",
      "fastapi_app.py lifespan, /api/health, /api/starters, / redirect")
async def tc38(ctx: Ctx) -> Outcome:
    c = await ctx.client(None)
    health = (await c.get("/api/health")).json()
    starters = (await c.get("/api/starters")).json()
    root = await c.get("/", follow_redirects=False)
    observed = {"status": health.get("status"), "ready": health.get("ready"),
                "starter_questions>0": len(starters.get("questions", [])) > 0,
                "root_redirects_to_welcome": root.status_code in (302, 307)
                and "welcome-page" in root.headers.get("location", "")}
    return await facts_check("GET /api/health, /api/starters, /", observed,
                             {"status": "ok", "ready": True, "starter_questions>0": True,
                              "root_redirects_to_welcome": True})


@case("TC-39", "Sign-in", "Condition testing (right / wrong password / unknown account)",
      "POST /api/auth/login, /api/auth/me, session cookie")
async def tc39(ctx: Ctx) -> Outcome:
    import httpx

    async with httpx.AsyncClient(base_url=ctx.base) as c:
        ok = await c.post("/api/auth/login", json={"username": " 441000003 ", "password": ctx.password})
        cookie = ok.headers.get("set-cookie", "").lower()
        me = await c.get("/api/auth/me")
    async with httpx.AsyncClient(base_url=ctx.base) as c:
        wrong = await c.post("/api/auth/login", json={"username": "441000003", "password": "nope-nope"})
        unknown = await c.post("/api/auth/login", json={"username": "nobody", "password": "nope-nope"})
        anon_me = await c.get("/api/auth/me")
    observed = {
        "valid_login": ok.status_code,
        "cookie_httponly": "httponly" in cookie,
        "me_after_login": me.json().get("user", {}).get("username"),
        "wrong_password": wrong.status_code,
        "unknown_account": unknown.status_code,
        "same_message_for_both": wrong.json() == unknown.json(),
        "me_without_session": anon_me.status_code,
    }
    return await facts_check("441000003 with right / wrong password, unknown user", observed,
                             {"valid_login": 200, "cookie_httponly": True, "me_after_login": "441000003",
                              "wrong_password": 401, "unknown_account": 401, "same_message_for_both": True,
                              "me_without_session": 401})


@case("TC-40", "Role-based access control", "Condition testing (role checks per route)",
      "src/accounts/deps.py require_roles, accounts API")
async def tc40(ctx: Ctx) -> Outcome:
    anon, st, adv, adm = (await ctx.client(None), await ctx.client(STUDENT),
                          await ctx.client(ADVISOR), await ctx.client(ADMIN))
    observed = {
        "anonymous -> /api/me/profile": (await anon.get("/api/me/profile")).status_code,
        "anonymous -> /api/chat": (await anon.post("/api/chat", json={"message": "x"})).status_code,
        "student -> /api/admin/users": (await st.get("/api/admin/users")).status_code,
        "student -> /api/advisor/students": (await st.get("/api/advisor/students")).status_code,
        "advisor -> /api/advisor/students": (await adv.get("/api/advisor/students")).status_code,
        "advisor -> /api/admin/files": (await adv.get("/api/admin/files")).status_code,
        "admin -> /api/admin/users": (await adm.get("/api/admin/users")).status_code,
        "admin -> /api/advisor/students": (await adm.get("/api/advisor/students")).status_code,
    }
    expected = {"anonymous -> /api/me/profile": 401, "anonymous -> /api/chat": 401,
                "student -> /api/admin/users": 403, "student -> /api/advisor/students": 403,
                "advisor -> /api/advisor/students": 200, "advisor -> /api/admin/files": 403,
                "admin -> /api/admin/users": 200, "admin -> /api/advisor/students": 200}
    return await facts_check("each role calls each protected route", observed, expected)


@case("TC-41", "Chat API end to end (student asks, cited answer returned)", "Path testing (HTTP -> auth -> workflow -> RAG -> JSON)",
      "POST /api/chat, workflow, retriever, LLM, citations")
async def tc41(ctx: Ctx) -> Outcome:
    st = await ctx.client(STUDENT)
    q, ref = GOLDEN[0]["question"], GOLDEN[0]["reference"]
    r = await st.post("/api/chat", json={"message": q, "history": []})
    body = r.json() if r.status_code == 200 else {}
    response = body.get("response", r.text)
    empty = await st.post("/api/chat", json={"message": "   "})
    too_long = await st.post("/api/chat", json={"message": "س" * 2001})
    ac = (await ctx.metrics["answer_correctness"].ascore(user_input=q, response=answer_body(response),
                                                          reference=ref)).value
    cited = (await _PRESENT.ascore(reference="المصادر:", response=response)).value
    scores = {"http_200": float(r.status_code == 200), "answer_correctness": round(float(ac), 4),
              "citation_present": cited, "blank_message_422": float(empty.status_code == 422),
              "over_2000_chars_422": float(too_long.status_code == 422)}
    thresholds = {"http_200": 1.0, "answer_correctness": RAG_THRESHOLDS["answer_correctness"],
                  "citation_present": 1.0, "blank_message_422": 1.0, "over_2000_chars_422": 1.0}
    return Outcome(q, ref, response, scores, thresholds, "http -> rag")


@case("TC-42", "Chat rate limit", "Condition testing (requests per minute > CHAT_RATE_LIMIT)",
      "fastapi_app._check_chat_rate")
async def tc42(ctx: Ctx) -> Outcome:
    app = ctx.app_module
    saved = app.CHAT_RATE_LIMIT
    app.CHAT_RATE_LIMIT = 2
    app._chat_hits.clear()
    try:
        st = await ctx.client(STUDENT_2)
        codes = [(await st.post("/api/chat", json={"message": "شكرا"})).status_code for _ in range(3)]
    finally:
        app.CHAT_RATE_LIMIT = saved
        app._chat_hits.clear()
    return await facts_check("3 messages with CHAT_RATE_LIMIT=2", {"status_codes": codes},
                             {"status_codes": [200, 200, 429]})


@case("TC-43", "Schedule API over HTTP", "Path testing + condition testing (valid / unknown code / bad time)",
      "POST /api/schedule/generate, GET /api/schedule/courses")
async def tc43(ctx: Ctx) -> Outcome:
    st = await ctx.client(STUDENT)
    anon = await ctx.client(None)
    courses = await st.get("/api/schedule/courses")
    ok = await st.post("/api/schedule/generate", json={"courses": ["ريض 1112", "عال 1140"]})
    bad_code = await st.post("/api/schedule/generate", json={"courses": ["XYZ 999"]})
    bad_time = await st.post("/api/schedule/generate", json={"courses": ["عال 1140"], "time_from": "8am"})
    anon_r = await anon.post("/api/schedule/generate", json={"courses": ["عال 1140"]})
    observed = {"courses": courses.status_code, "valid": ok.status_code,
                "valid_has_schedules": bool(ok.json().get("schedules")),
                "unknown_code": bad_code.status_code, "bad_time_format": bad_time.status_code,
                "anonymous": anon_r.status_code}
    return await facts_check("generate with valid and invalid input", observed,
                             {"courses": 200, "valid": 200, "valid_has_schedules": True,
                              "unknown_code": 422, "bad_time_format": 422, "anonymous": 401})


@case("TC-44", "Transcript upload API and profile storage", "Path testing (upload -> parse -> save in profile)",
      "POST /api/schedule/transcript, store.update_profile, GET /api/me/profile")
async def tc44(ctx: Ctx) -> Outcome:
    st = await ctx.client(STUDENT)
    txt = await st.post("/api/schedule/transcript", files={"file": ("t.txt", b"hello", "text/plain")})
    junk = await st.post("/api/schedule/transcript", files={"file": ("t.pdf", b"not a pdf", "application/pdf")})
    pdf = await st.post("/api/schedule/transcript",
                        files={"file": ("t.pdf", make_transcript_pdf(), "application/pdf")})
    profile = (await st.get("/api/me/profile")).json().get("profile", {})
    observed = {"txt_file": txt.status_code, "broken_pdf": junk.status_code, "valid_pdf": pdf.status_code,
                "completed": ",".join(pdf.json().get("completed", [])) if pdf.status_code == 200 else "",
                "saved_in_profile": bool(profile.get("transcript"))}
    return await facts_check("upload .txt, broken .pdf, valid transcript .pdf", observed,
                             {"txt_file": 415, "broken_pdf": 422, "valid_pdf": 200,
                              "completed": "عال 1100,عال 1140", "saved_in_profile": True})


@case("TC-45", "Advising tickets endpoint", "Condition testing (TICKETS_FILE off / on)",
      "POST /api/tickets, src/tickets.py")
async def tc45(ctx: Ctx) -> Outcome:
    import src.tickets as tickets

    anon = await ctx.client(None)
    payload = {"summary": "سؤال عن 1234567890", "transcript": [{"role": "user", "text": "x"}], "contact": "a@b.c"}
    saved = tickets.TICKETS_FILE
    try:
        tickets.TICKETS_FILE = ""
        off = await anon.post("/api/tickets", json=payload)
        tickets.TICKETS_FILE = os.path.join(TMP_DIR, "tickets.jsonl")
        on = await anon.post("/api/tickets", json=payload)
        with open(tickets.TICKETS_FILE, encoding="utf-8") as f:
            line = json.loads(f.readline())
    finally:
        tickets.TICKETS_FILE = saved
    observed = {"disabled": off.status_code, "enabled": on.status_code,
                "saved_status": line.get("status"), "number_masked": "1234567890" not in line.get("summary", "")}
    return await facts_check("POST /api/tickets with tickets off, then on", observed,
                             {"disabled": 503, "enabled": 200, "saved_status": "open", "number_masked": True})


@case("TC-46", "Saved chats, profile and planner", "Path testing (save -> list -> delete)",
      "/api/me/chats, /api/me/profile, /api/me/planner")
async def tc46(ctx: Ctx) -> Outcome:
    st = await ctx.client(STUDENT_2)
    put = await st.put("/api/me/chats/chat-ragas", json={"chat": {"id": "chat-ragas", "title": "اختبار", "messages": []}})
    listed = [c.get("id") for c in (await st.get("/api/me/chats")).json().get("chats", [])]
    bad_id = await st.put("/api/me/chats/bad id!", json={"chat": {}})
    deleted = await st.delete("/api/me/chats/chat-ragas")
    after = [c.get("id") for c in (await st.get("/api/me/chats")).json().get("chats", [])]
    prof = await st.put("/api/me/profile", json={"major": "علوم الحاسب", "level": "5"})
    plan = await st.put("/api/me/planner", json={"planner": {"courses": ["عال 1140"]}})
    observed = {"save": put.status_code, "listed": "chat-ragas" in listed, "invalid_chat_id": bad_id.status_code,
                "delete": deleted.status_code, "gone_after_delete": "chat-ragas" not in after,
                "profile_update": prof.status_code, "planner_save": plan.status_code}
    return await facts_check("chat-ragas, profile, planner", observed,
                             {"save": 200, "listed": True, "invalid_chat_id": 422, "delete": 200,
                              "gone_after_delete": True, "profile_update": 200, "planner_save": 200})


@case("TC-47", "Admin user management and temporary passwords", "Path testing (create -> first login -> forced change)",
      "/api/admin/users, /api/auth/password, deps.current_user")
async def tc47(ctx: Ctx) -> Outcome:
    import httpx

    adm = await ctx.client(ADMIN)
    created = await adm.post("/api/admin/users", json={"username": "ragas.new", "name": "New Student", "role": "student"})
    dup = await adm.post("/api/admin/users", json={"username": "ragas.new", "name": "Dup", "role": "student"})
    bad_role = await adm.post("/api/admin/users", json={"username": "ragas.x", "name": "X", "role": "admin"})
    temp = created.json().get("temporary_password", "")
    async with httpx.AsyncClient(base_url=ctx.base) as c:
        login = await c.post("/api/auth/login", json={"username": "ragas.new", "password": temp})
        blocked = await c.get("/api/me/profile")
        change = await c.post("/api/auth/password", json={"current_password": temp, "new_password": "my-new-pass-1"})
        unblocked = await c.get("/api/me/profile")
    uid = created.json().get("user", {}).get("id", "")
    disable = await adm.patch(f"/api/admin/users/{uid}", json={"active": False})
    async with httpx.AsyncClient(base_url=ctx.base) as c:
        disabled_login = await c.post("/api/auth/login", json={"username": "ragas.new", "password": "my-new-pass-1"})
    observed = {"create": created.status_code, "duplicate": dup.status_code, "admin_role_not_allowed": bad_role.status_code,
                "first_login": login.status_code, "before_password_change": blocked.status_code,
                "password_change": change.status_code, "after_password_change": unblocked.status_code,
                "disable": disable.status_code, "disabled_login": disabled_login.status_code}
    return await facts_check("admin creates ragas.new, who signs in with the temporary password", observed,
                             {"create": 201, "duplicate": 409, "admin_role_not_allowed": 422,
                              "first_login": 200, "before_password_change": 403, "password_change": 200,
                              "after_password_change": 200, "disable": 200, "disabled_login": 403})


@case("TC-48", "Admin source-document management", "Condition testing (allowed type / path traversal / duplicate)",
      "src/accounts/documents.py (/api/admin/files)")
async def tc48(ctx: Ctx) -> Outcome:
    adm = await ctx.client(ADMIN)
    sandbox = os.path.join(TMP_DIR, "docs")
    os.makedirs(os.path.join(sandbox, "regs"), exist_ok=True)
    saved = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = sandbox  # the real docs/ folder is never touched
    try:
        up = await adm.post("/api/admin/files", data={"folder": "regs"},
                            files={"file": ("rule.md", "# مادة\nنص".encode(), "text/markdown")})
        again = await adm.post("/api/admin/files", data={"folder": "regs"},
                               files={"file": ("rule.md", b"x", "text/markdown")})
        exe = await adm.post("/api/admin/files", data={"folder": "regs"},
                             files={"file": ("virus.exe", b"MZ", "application/octet-stream")})
        escape = await adm.post("/api/admin/files", data={"folder": "../.."},
                                files={"file": ("x.md", b"x", "text/markdown")})
        listing = (await adm.get("/api/admin/files")).json()
        removed = await adm.post("/api/admin/files/remove", json={"path": "regs/rule.md"})
    finally:
        if saved is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = saved
    observed = {"upload_md": up.status_code, "same_name_again": again.status_code,
                "exe_rejected": exe.status_code in (400, 415), "outside_docs_rejected": escape.status_code,
                "listed": any(f.get("path") == "regs/rule.md" for f in listing.get("files", [])),
                "index_marked_out_of_date": bool(listing.get("index", {}).get("stale")),
                "remove": removed.status_code,
                "removed_file_backed_up": any(os.scandir(os.environ["DOCS_BACKUP_DIR"]))}
    return await facts_check("upload rule.md, again, virus.exe, ../.. ; then remove", observed,
                             {"upload_md": 201, "same_name_again": 409, "exe_rejected": True,
                              "outside_docs_rejected": 400, "listed": True, "index_marked_out_of_date": True,
                              "remove": 200, "removed_file_backed_up": True})


# ------------------------------------------------------------------- GUI

PAGES = {
    "sign-in-page": ["Academic AI - Sign In", 'id="auth-form"', 'id="university-id"', 'id="password"'],
    "welcome-page": ["Choose Your Workspace", 'id="welcome-name"', 'id="sign-out-btn"'],
    "chatbot-page": ["AI Chatbot", 'id="new-chat-btn"', 'id="history"'],
    "schedule-page": ["Study Schedule", 'id="open-import-btn"', 'id="stat-credits"'],
    "profile-page": ["My Profile", 'id="id-name"'],
    "advisor-page": ["Advising", 'id="student-count"', 'id="search"'],
    "admin-page": ["Admin Console", 'id="tab-docs"', 'id="tab-accounts"'],
}


@case("TC-49", "GUI pages are served with their key controls", "Code coverage (critical requirement)",
      "frontend/* pages served by /app, shared/auth.js")
async def tc49(ctx: Ctx) -> Outcome:
    anon = await ctx.client(None)
    scores, missing = {}, []
    html_all = []
    for page, needles in PAGES.items():
        r = await anon.get(f"/app/{page}/index.html")
        scores[f"{page}_200"] = float(r.status_code == 200)
        for n in needles:
            s = (await _PRESENT.ascore(reference=n, response=r.text)).value
            scores[f"{page}:{n}"] = s
            if not s:
                missing.append(f"{page}:{n}")
        html_all.append(f"{page}: {r.status_code}, {len(r.text)} bytes")
    for asset in ("shared/auth.js", "chatbot-page/script.js", "schedule-page/script.js"):
        r = await anon.get(f"/app/{asset}")
        scores[f"{asset}_200"] = float(r.status_code == 200)
    expected = "; ".join(f"{p}: {', '.join(n)}" for p, n in PAGES.items())
    return Outcome("GET /app/<page>/index.html for 7 pages", expected,
                   "\n".join(html_all) + (f"\nmissing: {missing}" if missing else ""),
                   scores, {k: 1.0 for k in scores})


@case("TC-50", "GUI scripts call only existing API routes", "Condition testing (front-end/back-end contract)",
      "frontend/*/script.js fetch() calls vs FastAPI routes")
async def tc50(ctx: Ctx) -> Outcome:
    app = ctx.app_module.app
    # FastAPI >= 0.13x nests included routers (_IncludedRouter) inside
    # app.routes, so the OpenAPI schema is the flat list of real API paths.
    routes = set(app.openapi()["paths"]) | {getattr(r, "path", "") for r in app.routes}
    called = set()
    for page in os.listdir("frontend"):
        for name in ("script.js", "auth.js"):
            p = os.path.join("frontend", page, name)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    called |= set(re.findall(r"""["'`](/api/[A-Za-z0-9_/\-]+)""", f.read()))

    def known(path: str) -> bool:
        if path in routes:
            return True
        pattern = lambda r: re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", r) + "/?", path)  # noqa: E731
        return any(pattern(r) or r.startswith(path.rstrip("/") + "/") for r in routes)

    unknown = sorted(p for p in called if not known(p))
    return await facts_check(f"{len(called)} distinct /api paths in the pages' scripts",
                             {"unknown_routes": unknown}, {"unknown_routes": []})


# ================================================================ runner


async def start_server(ctx: Ctx):
    import uvicorn

    import fastapi_app
    from src.accounts import store

    ctx.app_module = fastapi_app
    ctx.password = os.getenv("PRESET_PASSWORD", "").strip() or store.DEFAULT_PRESET_PASSWORD
    config = uvicorn.Config(fastapi_app.app, host="127.0.0.1", port=PORT, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    t0 = time.monotonic()
    while not server.started:
        if task.done():
            raise RuntimeError(f"server failed to start: {task.exception()!r}")
        if time.monotonic() - t0 > 240:
            raise TimeoutError("server did not start in 240 s")
        await asyncio.sleep(0.2)
    log.info("Server up on %s in %.1fs", ctx.base, time.monotonic() - t0)
    ctx.workflow = fastapi_app.workflow
    ctx.recorder = RecordingTool(ctx.workflow._query_engine_tool)
    ctx.workflow._query_engine_tool = ctx.recorder
    return server, task


def judge(res: Result) -> str:
    for k, th in res.thresholds.items():
        v = res.scores.get(k)
        if v is None or v < th:
            return "FAIL"
    return "PASS"


async def run(only: set[str] | None):
    ctx = Ctx()
    log.info("RAGAS suite %s | judge=%s | log=%s", STAMP, JUDGE_MODEL, LOG_PATH)
    server, task = await start_server(ctx)
    results: list[Result] = []
    try:
        for cid, task_name, technique, components, fn in sorted(CASES, key=lambda c: c[0]):
            if only and cid not in only:
                continue
            res = Result(cid, task_name, technique, components)
            t0 = time.monotonic()
            log.info("▶ %s %s", cid, task_name)
            try:
                out = await fn(ctx)
                res.input, res.expected, res.actual = out.input, out.expected, out.actual
                res.scores, res.thresholds, res.route = out.scores, out.thresholds, out.route
                res.contexts = [c[:300] for c in out.contexts]
                res.status = judge(res)
            except Exception as e:
                res.status = "ERROR"
                res.error = "".join(traceback.format_exception(e))
                log.error("%s raised:\n%s", cid, res.error)
            res.seconds = round(time.monotonic() - t0, 2)
            failed = {k: v for k, v in res.scores.items() if v is None or v < res.thresholds.get(k, 0)}
            log.info("  %s %s (%.1fs) scores=%s%s", res.status, cid, res.seconds,
                     json.dumps(res.scores, ensure_ascii=False),
                     f" FAILED={json.dumps(failed, ensure_ascii=False)}" if failed else "")
            if res.status != "PASS":
                log.info("  expected: %s", res.expected[:400])
                log.info("  actual:   %s", res.actual[:400])
            results.append(res)
    finally:
        for c in ctx.clients.values():
            await c.aclose()
        server.should_exit = True
        await task
    write_reports(results)
    return results


def write_reports(results: list[Result]):
    json_path = os.path.join(OUT_DIR, f"results_{STAMP}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)
    rag = [r for r in results if r.id in {g["id"] for g in GOLDEN}]
    means = {}
    for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall", "answer_correctness"):
        vals = [r.scores.get(k) for r in rag if r.scores.get(k) is not None]
        if vals:
            means[k] = round(sum(vals) / len(vals), 4)
    passed = sum(r.status == "PASS" for r in results)
    lines = [f"# RAGAS run {STAMP}", "", f"Judge: {JUDGE_MODEL}. Passed {passed}/{len(results)}.", "",
             "RAG means: " + json.dumps(means, ensure_ascii=False), "",
             "| ID | Task | Technique | Status | Scores |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.id} | {r.task} | {r.technique} | {r.status} | "
                     f"{json.dumps(r.scores, ensure_ascii=False)} |")
    md_path = os.path.join(OUT_DIR, f"report_{STAMP}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log.info("SUMMARY passed %d/%d | RAG means %s", passed, len(results), means)
    log.info("Wrote %s and %s", json_path, md_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*", help="run only these test case ids")
    args = parser.parse_args()
    results = asyncio.run(run(set(args.only) if args.only else None))
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    sys.exit(0 if all(r.status == "PASS" for r in results) else 1)


if __name__ == "__main__":
    main()
