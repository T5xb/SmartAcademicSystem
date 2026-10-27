# Smart Academic Advising System — RAG chatbot (GP2, Group M3)

Answers Arabic questions about IMSIU academic regulations strictly from the
official documents in `docs/`, with a citation (document + page + article)
resolved from the actual retrieved text.

## Repository layout

| path | what it is |
| --- | --- |
| `fastapi_app.py`, `src/` | RAG chatbot server (API on port 8000) |
| `src/scheduling/` | CSP study-schedule generator + transcript import (same server, `/api/schedule/*`) |
| `frontend/` | GP2 web pages: `sign-in-page` → `welcome-page` → `chatbot-page` / `schedule-page` |
| `docs/` | official regulation documents that answers are drawn from |

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
http://localhost:8000 in the browser (any email/password signs in for the
demo). To share it, double-click `Start-Public.bat` instead: it also prints
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
.venv/Scripts/python.exe SmartAcademicSystem.py   # Gradio UI  -> http://127.0.0.1:7860
.venv/Scripts/python.exe fastapi_app.py           # GP2 web pages -> http://localhost:8000
.venv/Scripts/python.exe fastapi_app.py --public  # same, plus a public ngrok link
```

`fastapi_app.py` also exposes the chatbot as JSON for any other front end:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"ما هي إجراءات الانسحاب من مقرر؟"}'
```

### GP2 web front end (`frontend/chatbot-page`)

`fastapi_app.py` serves the GP2 pages itself under `/app` (`/` redirects
there; the old minimal chat page is at `/simple`), so the pages and the
API share one address. Besides `POST /api/chat` the chatbot page uses:

| endpoint | used for |
| --- | --- |
| `GET /api/health` | the live "Server online / offline" pill and latency |
| `GET /api/starters` | suggested questions (`NEXT_PUBLIC_STARTER_QUESTIONS`) |

The pages call the server they were loaded from; opened straight from
disk (`file://`) they fall back to `http://localhost:8000`. CORS is open by
default so that still works — set
`CORS_ORIGINS` in `src/.env` (comma-separated) to restrict it.

## Which LLM answers

Set `LLM_PROVIDER` in `src/.env`:

| value | what runs | speed | Arabic quality |
| --- | --- | --- | --- |
| `hosted` | `LLM_MODEL` via `LLM_API_BASE` (default `qwen/qwen3.8-27b` on Groq) | ~3 s | good, cites per fact |
| `ollama` | `llama3.2:3b` on this CPU | ~37 s | weak (mixes languages, drops citations) |

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

Compare the two on identical questions:

```bash
.venv/Scripts/python.exe scripts/bench.py --provider ollama
.venv/Scripts/python.exe scripts/bench.py --provider hosted
```

## Letting your team reach it remotely

By default `SmartAcademicSystem.py` only listens on `127.0.0.1` — nobody
outside this machine can open it. To give teammates a real link:

1. Free token from https://dashboard.ngrok.com/get-started/your-authtoken
2. Paste it into `NGROK_AUTHTOKEN` in `src/.env`
3. Run `SmartAcademicSystem.py` as usual — it prints a `Public (share with
   team)` link alongside the local one

That link is only live while this process keeps running, and changes on
every restart (free ngrok tier) — resend it to the team each time you
restart. Without a token, it falls back to Gradio's own `share=True`
tunnel — no signup needed, but on this network that tunnel's connection is
blocked by the firewall (the binary downloads fine, then the link never
comes up), which is why `NGROK_AUTHTOKEN` is the reliable option here.
