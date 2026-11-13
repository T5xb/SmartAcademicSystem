# Smart Academic Advising System — RAG chatbot (GP2, Group M3)

Answers Arabic questions about IMSIU academic regulations strictly from the
official documents in `docs/`, with a citation (document + page + article)
resolved from the actual retrieved text.

## Repository layout

| path | what it is |
| --- | --- |
| `fastapi_app.py`, `src/` | RAG chatbot server (API on port 8000) |
| `src/scheduling/` | CSP study-schedule generator + transcript import (same server, `/api/schedule/*`) |
| `src/accounts/` | accounts, sign-in sessions and roles; the admin's document management |
| `frontend/` | GP2 web pages: `sign-in-page`, then by role: `welcome-page` → `chatbot-page` / `schedule-page` / `profile-page` (student), `advisor-page`, `admin-page` |
| `docs/` | official regulation documents that answers are drawn from |
| `scripts/` | OCR for scanned PDFs (`ocr_pdf.py`) |
| `tests/` | pytest suite (`uv run pytest`) |
| `evaluation/` | RAGAS test suite for every task (see "Testing with RAGAS") |
| `Start-API.bat`, `Start-Public.bat` | double-click launchers (local / with a public ngrok link) |

## Quick start for teammates

The Supabase index is already built and shared — **do not** re-run
`generate` (it drops and rebuilds the shared table).

```bash
python -m pip install uv          # once
uv sync                           # creates .venv with Python 3.11–3.13
ollama pull bge-m3                # once, ~1.2 GB (install Ollama first)
copy src\.env.example src\.env    # then paste the team's keys into src\.env
```

Get the real `src/.env` values (Groq key, Supabase URL) from the team
privately — **never commit `src/.env`** (it is git-ignored).

Then double-click `Start-API.bat`: it starts the server and opens
http://localhost:8000 in the browser (sign in with a preset account, see
"Accounts and roles" below). To share it, double-click `Start-Public.bat` instead: it also prints
a public ngrok link (needs `NGROK_AUTHTOKEN` in `src/.env`; set
`NGROK_DOMAIN` to a free ngrok static domain to keep the same link every
run). The link only works while that window and this laptop stay on.

## Architecture

| layer | where it runs |
| --- | --- |
| Answer generation | hosted, any OpenAI-compatible API (default: Qwen3.8 27B on Groq) |
| Vector store | Supabase Postgres + pgvector |
| Embeddings | local Ollama (`bge-m3`) — at index time **and** per query |
| Document loading / OCR | local, one-off (`scripts/ocr_pdf.py`) |

Embeddings being local is the one non-serverless piece: a deployed
instance needs a reachable `OLLAMA_BASE_URL` to embed incoming questions.
To go fully hosted, set `EMBEDDING_PROVIDER=openai`, add `OPENAI_API_KEY`,
set `EMBED_DIM=1536`, and re-run `generate` (the vectors must be rebuilt —
pgvector fixes the column width at creation).

## Setup

1. **LLM key** — free key from https://console.groq.com/keys into
   `LLM_API_KEY` in `src/.env`.
2. **Database** — create a Supabase project, then copy *Project Settings →
   Database → Connection string → URI* into `SUPABASE_DB_URL` in
   `src/.env`. `pgvector` is enabled automatically on first index build
   (`CREATE EXTENSION IF NOT EXISTS vector`).
3. **Embeddings + index**:

```bash
ollama pull bge-m3            # ~1.2 GB, local
.venv/Scripts/python.exe -c "from src.generate import generate_index; generate_index()"
```

Re-running step 3 drops and rebuilds the `data_academic_advising` table,
so it never accumulates stale chunks.

## Run

```bash
.venv/Scripts/python.exe fastapi_app.py           # GP2 web pages -> http://localhost:8000
.venv/Scripts/python.exe fastapi_app.py --public  # same, plus a public ngrok link
```

`fastapi_app.py` also exposes the chatbot as JSON for any other front end:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"ما هي إجراءات الانسحاب من مقرر؟"}'
```

### Testing with RAGAS

`evaluation/ragas_suite.py` runs 50 test cases against the real system
(it starts the server itself, uses the live index, Ollama and the hosted
model, and a throwaway accounts database). RAG answers are scored by an
LLM judge; every other task by RAGAS ExactMatch / StringPresence.

```bash
uv sync --extra eval
.venv/Scripts/python.exe -m evaluation.ragas_suite                  # all 50 cases
.venv/Scripts/python.exe -m evaluation.ragas_suite --only TC-11     # chosen cases
```

Results, answers, retrieved chunks and the log go to `output/ragas/`. The
judge is `openai/gpt-oss-20b` (override with `RAGAS_JUDGE_MODEL`); a full
run uses about 160K of its 200K free tokens per day, so re-run only the
cases you changed. Judge answers are cached in `output/ragas/judge_cache`.

### GP2 web front end (`frontend/chatbot-page`)

`fastapi_app.py` serves the GP2 pages itself under `/app` (`/` redirects
there), so the pages and the
API share one address. Besides `POST /api/chat` the chatbot page uses:

| endpoint | used for |
| --- | --- |
| `GET /api/health` | the live "Server online / offline" pill and latency |
| `GET /api/starters` | suggested questions (`NEXT_PUBLIC_STARTER_QUESTIONS`) |

`POST /api/chat` also takes `history` (the chat's last messages,
`[{"role": "user"|"bot", "text": ...}]`, oldest first). The server uses it
only to count its clarifying questions and stores nothing.

### Unclear questions and advising tickets

If a question is unclear or the documents don't answer it, the bot asks
the student to clarify (up to `MAX_CLARIFY_ATTEMPTS`, default 2) before
suggesting a ticket with academic advising. Settings in `src/.env`:

| setting | effect |
| --- | --- |
| `MAX_CLARIFY_ATTEMPTS` | clarifying questions before the ticket suggestion |
| `TICKET_URL` | link added to the ticket suggestion (empty = text only) |
| `TICKETS_FILE` | turns on `POST /api/tickets` and saves tickets there as JSON lines (empty = off) |

When the reply suggests a ticket, the `/api/chat` response also carries a
`ticket` draft for the future ticket page / advisors' dashboard. Shape and
details: [ARCHITECTURE.md §4.6](ARCHITECTURE.md).

### Accounts and roles

Everything except the sign-in page needs an account. The first start
creates five preset accounts with the password in `PRESET_PASSWORD`
(`src/.env`, default `test12345`):

| ID | role | opens |
| --- | --- | --- |
| `admin` | admin | `admin-page`: source documents (view, upload, replace, remove, OCR), index rebuild, accounts (add, disable, reset password) |
| `advisor` | academic advisor | `advisor-page`: the students and each one's academic profile |
| `441000001` – `441000003` | student | chatbot (chats saved to the account), schedule planner, profile |

Accounts, sessions, saved chats and profiles are stored in the same
Supabase database as the index, in tables named `sas_*`. Passwords are
stored as scrypt hashes; the session is an HttpOnly cookie. An account the
admin adds gets a one-time password that must be changed at first sign-in.

Replacing a document: in the admin page, find the old file (search or
folder filter) and use **Replace** on its row. The new file takes its place
in the same folder, the old one moves to `output/replaced_docs/`, and the
page asks for an index rebuild. The chatbot can't answer during the few
minutes a rebuild takes.

The pages must be opened from the server (`http://localhost:8000` or the
public link), not from disk: the session cookie only goes to the server
the page came from. Set `CORS_ORIGINS` in `src/.env` (comma-separated) to
restrict which other sites may call the public routes.

## Which LLM answers

Set `LLM_PROVIDER` in `src/.env`:

| value | what runs | Arabic quality |
| --- | --- | --- |
| `hosted` | `LLM_MODEL` via `LLM_API_BASE` (default `qwen/qwen3.8-27b` on Groq) | good, cites per fact |
| `ollama` | `llama3.2:3b` on this CPU (much slower) | weak (mixes languages, drops citations) |

Only answer generation differs between the two; retrieval and embeddings
are the same either way. Only public regulation text is ever sent to the
hosted provider — no student data.

The hosted path is built on `OpenAILike`, not a vendor-specific client, so
switching Groq → OpenRouter/Together/self-hosted vLLM is three env vars
(`LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`) and no code change. Qwen stays
the model family — its Arabic quality is what GP2 validated.

Leaving `LLM_PROVIDER` blank auto-selects `hosted` when `LLM_API_KEY` is
present and falls back to `ollama` otherwise, so the demo still answers if
the key expires or the network drops.

## Letting your team reach it remotely

Run `Start-Public.bat` (or `fastapi_app.py --public`) to get a public ngrok
link alongside the local one:

1. Free token from https://dashboard.ngrok.com/get-started/your-authtoken
2. Paste it into `NGROK_AUTHTOKEN` in `src/.env` (optionally `NGROK_DOMAIN`
   for a free static domain, so the link stays the same between runs)
3. Run `Start-Public.bat` — it prints a `Public (share it)` link

That link is only live while this process (and this laptop) keeps running.
