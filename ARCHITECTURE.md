# Architecture & Design Decisions

Reference for the team (Group M3) and raw material for the GP2 report.
Covers how the RAG chatbot works end to end, and *why* each piece is the
way it is. Code comments stay short and point here.

---

## 1. What this is (and what it is not)

No model was trained or fine-tuned. This is **Retrieval-Augmented
Generation (RAG)**: a general-purpose LLM is handed the relevant passage
from the official regulations *inside each prompt*, and answers only from
that. Fine-tuning would need large training sets and GPU hours, and would
still leave answers unattributable — RAG keeps every answer traceable to a
document, page and article, which is what an academic-regulations
assistant actually needs.

Implements GP1 Use Case 2 (*Ask Academic Question via Chatbot*) and
Use Case 3 (*Receive Source-Based Answer*). CSP study-schedule generation
and transcript import are in `src/scheduling/` (section 7); sign-in remains
unbuilt.

## 2. Request flow

```
Arabic question
      │
      ▼  bge-m3 via local Ollama
question → 1024-dim vector
      │
      ▼  cosine distance, exact scan over 118 chunks
Supabase Postgres + pgvector → top 8 chunks
      │
      ▼  Arabic prompt: chunks + question + strict rules
Qwen3.8 27B via Groq (OpenAI-compatible API)
      │
      ▼  code (not the LLM) resolves citation ids → real sources
answer + "المصادر" section
```

Files: [src/settings.py](src/settings.py) (models) →
[src/index.py](src/index.py) (vector store) →
[src/query.py](src/query.py) (retriever) →
[src/citation.py](src/citation.py) (prompts + citations) →
[src/clarify.py](src/clarify.py) (unclear questions, §4.6) →
[src/workflow.py](src/workflow.py) (orchestration).

## 3. Indexing pipeline (run once, `generate`)

[src/generate.py](src/generate.py) loads `docs/`, chunks it, embeds it and
writes to Supabase. Three loaders, because Arabic documents break the
defaults:

| Input | Problem | Solution |
| --- | --- | --- |
| Text PDFs | LlamaIndex's default pypdf reader scrambles RTL word order | PyMuPDF instead ([src/pdf_loader.py](src/pdf_loader.py)) |
| Scanned PDF (35 pages) | No text layer at all — `get_text()` returned 0 chars | EasyOCR (ar+en) via [scripts/ocr_pdf.py](scripts/ocr_pdf.py), run manually once |
| `.docx` | none | `SimpleDirectoryReader` |

Both PDF and OCR loaders emit **one Document per page**, so `page_label`
survives into chunk metadata — that is where citation page numbers come
from.

OCR needed two engineering fixes: it kept dying from out-of-memory
(solved with `dpi=130` and `canvas_size=1280`, since the detector's
memory scales with the square of canvas size), and a crash lost all
progress (solved by flushing each page to disk immediately and skipping
already-completed pages on restart).

**Chunking:** 400 chars with 80 overlap. The default 1024 merged
unrelated content into one chunk (a cover page + a decree + several
definitions), which confused the model even when the right fact was
present. Overlap prevents an article being cut mid-sentence.

## 4. Key decisions

### 4.1 Embeddings: `bge-m3`, kept local

Originally `nomic-embed-text`, which is English-trained. Arabic questions
matched the right Arabic chunk only weakly — the correct article often
ranked ~10th, which is why `TOP_K` had been pushed to 12 just to catch
it. `bge-m3` is explicitly multilingual: the correct article now ranks
**#1** for all three starter questions, so `TOP_K` came down to 8 (less
noise, faster, more accurate).

Kept local rather than hosted: no extra key or spend, reproducible
offline, and query embedding is fast enough on CPU. **Cost of this
choice:** embeddings run per *query* too, not only at index time, so a
deployed instance needs a reachable Ollama — the system is not purely
serverless. To go fully hosted: `EMBEDDING_PROVIDER=openai`,
`EMBED_DIM=1536`, then re-run `generate` (vectors must be rebuilt;
pgvector fixes column width at creation).

### 4.2 LLM: Qwen3.8 27B, hosted, provider-agnostic

Measured on real questions from `docs/` rather than chosen by reputation:

| Model | Latency | Outcome |
| --- | --- | --- |
| `qwen/qwen3.8-27b` | 2.7 s | full answer, **a citation per fact** — chosen |
| `openai/gpt-oss-120b` | 3.2 s | correct, but lumps all citations at the end |
| `allam-2-7b` (SDAIA) | 1.6 s | repeated itself, no usable citations |
| `llama3.2:3b` (local baseline) | 37–52 s | mixes languages mid-sentence, drops citations |

ALLaM was tested specifically because a Saudi Arabic-first model suits an
IMSIU project — it failed on merit (7B, 4096-token context), so the
decision rests on measurement, not preference.

Built on `OpenAILike`, **not** a vendor-specific client, so moving to
OpenRouter / Together / self-hosted vLLM is three env vars and no code
change. Qwen stays the model family; only the provider is swappable.

Why hosted at all — GP1 §3.3.2 requires *"respond within an acceptable
time"* and *"support multiple users simultaneously"*. A CPU-only local
model takes ~40 s and serves one user. "Fully local" appears nowhere in
GP1; the hosted path violates no stated requirement, and only public
regulation text is ever sent (no student data).

The local Ollama path is kept as the offline fallback and as the measured
baseline for the report — `scripts/bench.py --provider ollama`.

### 4.3 Vector store: Supabase Postgres + pgvector

Replaced a local `chroma_db/` folder, which meant every app instance
needed its own copy on its own disk and lost it on restart with ephemeral
storage. Managed Postgres is shared, durable and reachable by several
instances — what "multiple users simultaneously" actually requires.

Uses `llama-index-vector-stores-postgres` (`PGVectorStore`) rather than
the `-supabase` package: Supabase *is* Postgres with pgvector so both
reach the same database, but the postgres integration is actively
maintained, has real metadata-filter support (our citations depend on
metadata), and keeps any Postgres host viable later.

**Similarity:** pgvector's `cosine_distance` (`<=>`). Worth noting for the
report — the previous Chroma setup defaulted to L2, which only *ranked*
equivalently to cosine because bge-m3 vectors are unit-normalised. This
is now literally cosine similarity.

**No ANN index on purpose.** No `hnsw_kwargs`, so pgvector does an exact
scan. At 118 chunks that is faster than an index probe *and* more
accurate — HNSW is approximate and can miss the true nearest chunk, which
for a cited answer is a wrong-source risk. Revisit at thousands of chunks
(parameters are in [src/index.py](src/index.py)).

### 4.4 Two connection gotchas (both were silent failures)

1. **Direct connection is unusable on our network.** Supabase serves
   `db.<ref>.supabase.co` over **IPv6 only**, and the dev machine has no
   IPv6 route (100% packet loss). The **session pooler** host
   (`aws-0-ap-southeast-1.pooler.supabase.com:5432`, IPv4) is required —
   Supabase's own dashboard recommends it "when connecting via an IPv4
   network".
2. **`sslmode` and prepared statements.** Supabase URIs carry
   `?sslmode=require`, which psycopg2 understands and asyncpg rejects — so
   the async URL is stripped of it (TLS is still negotiated). And the
   transaction-mode pooler (port 6543) cannot keep per-session prepared
   statements, which asyncpg uses by default; that surfaces as
   intermittent `prepared statement ... already exists` errors under
   concurrency — exactly what a shared demo produces. Fixed with
   `prepared_statement_cache_size=0` (SQLAlchemy's documented fix for
   pgbouncer-style poolers). See `sqlalchemy_urls` in
   [src/index.py](src/index.py).

### 4.5 Citations are built by code, never by the LLM

The model emits only an opaque `[citation:<node_id>]` tag. Our code maps
that id back to the **actual retrieved chunk** and prints its real file
name, page and article. Asking an LLM to transcribe a filename and page
number invites a confidently wrong source; copying an opaque id it was
just given is a far easier task. Tags matching no retrieved node are
dropped rather than shown.

Article numbers are extracted by regex from chunk text. The original
pattern matched `المادة` + one token, which collapsed **المادة الثانية
عشرة** (art. 12), **المادة الثانية والعشرون** (art. 22) and **المادة
الثانية** (art. 2) into the same label — citations pointed at the wrong
article — and also matched OCR noise like `المادة )`. The current pattern
uses a closed ordinal set plus an optional "tens" tail (including the
missing-waw spelling the OCR produces): 50 articles matched, zero noise.

### 4.6 Unclear or unanswered questions: clarify first, then a ticket

When the documents don't answer, or the message has no topic at all
("عندي مشكلة"، "ممكن سؤال؟"), the bot asks the student to clarify instead of
sending them straight to advising ([src/clarify.py](src/clarify.py)):

1. Detection: the model's no-answer sentinel (as before, emitted by the
   model, interpreted by code), or a message that only says "I have a
   question" with no topic word — that one skips retrieval and the LLM.
2. Up to `MAX_CLARIFY_ATTEMPTS` (default 2) short clarifying questions in
   the group's style. The student's answers are searched together with
   their first message, so "عندي مشكلة بالغياب" + "كم النسبة اللي تحرمني؟"
   is one question.
3. Still nothing: the reply suggests opening a ticket with academic
   advising. Text only until the ticket page exists; `TICKET_URL` adds a
   link to it.

The attempt count comes from the last messages the chat page sends with
each question (`history` in `POST /api/chat`), so nothing is stored on the
server. Clarifying replies carry a fixed marker (`🤔|`) that code, not the
model, writes and later counts.

**Hook for the advisors' dashboard** ([src/tickets.py](src/tickets.py)):
when the reply suggests a ticket, `/api/chat` also returns `ticket`, a draft
(`id`, `created_at`, `status`, `summary`, `transcript`, `contact`) with
long numbers and e-mails masked. A ticket page can post it to
`POST /api/tickets` (`{summary, transcript, contact}`), which calls
`create_ticket()`. That is off (503) until `TICKETS_FILE` is set, and then
only appends JSON lines to that file; swap its body for the dashboard's
database when it exists.

### 4.7 Free-tier limits shaped two settings

Groq's free tier enforces an output-tokens-per-minute budget against each
request's *expected* output. With `max_tokens` unset, that expectation is
the model's full 16384-token limit, which alone exceeds the budget and
returns 429 **before generating any text**. Hence `max_tokens=512`
(a grounded answer runs ~300) and `max_retries=3`.

`context_window` is the model's real limit (131042, read from Groq's live
model list), not LlamaIndex's 3900-token fallback for unknown model ids —
that fallback would have split our retrieved chunks across several needless
"refine" calls.

## 5. Measured results

- **Retrieval:** correct article ranks #1 on all three starter questions.
- **Latency:** ~1–3 s hosted vs 37–52 s local.
- **Concurrency:** 8 simultaneous async retrievals, 4.54 s wall, zero
  failures (sequential would be ~35 s).
- **Index:** 38 documents → 118 chunks, 1024-dim, metadata intact.

Reproduce with `scripts/bench.py` (see README).

## 6. Known gaps

- Sign-in: not built (the pages accept any email/password for the demo).
- No conversational memory — each question is answered independently.
- **No quantitative accuracy metric.** GP1 §2.5 promises
  "Performance Evaluation & Metrics"; we have latency and manual spot
  checks but no scored benchmark set. Building ~20 questions with
  reference answers is the highest-value next step before the defense.
- Public access currently depends on an ngrok tunnel from a laptop: the
  URL changes every restart and dies when the machine sleeps. Real student
  access needs proper hosting (and then an answer for the local-Ollama
  embedding dependency in §4.1).
- `data_academic_advising` has no row-level security. Fine while only the
  server connects, but must be addressed before any public deployment.

## 7. Study-schedule generator (CSP)

`frontend/schedule-page` calls three routes on the same server
([src/scheduling/api.py](src/scheduling/api.py)), so one `Start-API.bat`
runs both the chatbot and the scheduler:

| Route | What it does |
| --- | --- |
| `GET /api/schedule/courses` | the CS study plan (`course_data.py`) as JSON |
| `POST /api/schedule/generate` | validates the selection, runs the CSP, returns schedules best-first |
| `POST /api/schedule/transcript` | parses a transcript PDF (pdfplumber), maps its codes to plan codes, suggests next-term courses |

The solver ([csp_scheduler.py](src/scheduling/csp_scheduler.py)) is a
backtracking CSP with node consistency, MRV, LCV and forward checking.
Hard constraints: no lecture clash (H2), no two finals in the same slot
(H3), open seats (H5), locked sections (H6), time window and minimum days
off (H7). Before solving, [validation.py](src/scheduling/validation.py)
checks the credit-hour limit, the 3-elective limit and, only after a
transcript import, prerequisites. Schedules are ranked by
`evaluate_schedule` (free days, idle gaps, morning preference, instructor
preference).

The transcript is parsed in memory and never stored. Section times and
instructors in `course_data.py` are still placeholders until the real
offered-sections timetable is available.

Tests: `.venv/Scripts/python.exe -m tests.test_csp_scheduler` and
`.venv/Scripts/python.exe -m tests.test_schedule_service`.
