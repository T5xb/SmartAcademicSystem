
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv("src/.env")

# Imported after load_dotenv() so DATA_DIR picks up an .env override, if any.
from src.clarify import MAX_HISTORY  # noqa: E402
from src.index import DATA_DIR  # noqa: E402
from src.scheduling.api import router as schedule_router  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gp2-chatbot")

workflow = None
# Suggested questions for the chat page, read once from .env at startup.
starter_questions: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global workflow, starter_questions
    from src.workflow import create_workflow

    logger.info("Loading index and building workflow...")
    workflow = create_workflow()

    starter_raw = os.getenv("NEXT_PUBLIC_STARTER_QUESTIONS", "[]")
    try:
        starter_questions = json.loads(starter_raw)
    except json.JSONDecodeError:
        starter_questions = []

    logger.info("Ready.")
    yield


app = FastAPI(title="GP2 RAG Chatbot", lifespan=lifespan)

# The GP2 pages are normally served by this server (/app), but can still be
# opened straight from disk (file://) or another port, which needs CORS.
# Override with a comma-separated CORS_ORIGINS list to lock this down.
cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Study-schedule generator (CSP) used by frontend/schedule-page.
app.include_router(schedule_router)

# Serve any files the user drops in DATA_DIR (optional, handy for debugging)
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")

# The GP2 web pages (sign-in, welcome, chatbot, schedule) are served from the
# same server, so one run and one link (local or public) is all a user needs.
# The folder layout is kept, so the pages' relative links keep working.
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


class ChatTurn(BaseModel):
    role: Literal["user", "bot"]
    text: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # The conversation so far (oldest first), used only to count the bot's
    # clarifying questions in this chat. Not stored.
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


class ChatResponse(BaseModel):
    response: str
    # A ticket draft when the reply suggests opening a ticket (see
    # src/tickets.py); the future ticket page posts it to /api/tickets.
    ticket: dict | None = None


class TicketRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    transcript: list[ChatTurn] = Field(default_factory=list, max_length=40)
    contact: str = Field(default="", max_length=200)


@app.get("/api/health")
async def health():
    return {"status": "ok", "ready": workflow is not None}


@app.get("/api/starters")
async def starters():
    return {"questions": starter_questions}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message is empty.")
    try:
        history = [t.model_dump() for t in req.history[-MAX_HISTORY:]]
        response, ticket = await workflow.respond(message, history)
    except Exception:
        # Retrieval or the LLM provider failed (rate limit, network, DB);
        # the front end shows this detail in its error card.
        logger.exception("Chat request failed")
        raise HTTPException(
            status_code=502,
            detail="The advising service could not generate an answer right now. Please try again.",
        )
    return ChatResponse(response=response, ticket=ticket)


@app.post("/api/tickets")
async def tickets(req: TicketRequest):
    """
    Hook for the advisors' dashboard: saves a student's ticket. Off until
    TICKETS_FILE is set in src/.env; see src/tickets.py for the shape.
    """
    from src.tickets import build_ticket, create_ticket, tickets_enabled

    if not tickets_enabled():
        raise HTTPException(status_code=503, detail="Tickets are not enabled yet.")
    ticket = build_ticket(req.summary, [t.model_dump() for t in req.transcript])
    # Given by the student on the ticket page on purpose, so not masked.
    ticket["contact"] = req.contact.strip()
    create_ticket(ticket)
    return {"id": ticket["id"], "status": ticket["status"]}


@app.get("/", include_in_schema=False)
async def index():
    # The welcome page sends visitors without a session to sign-in first.
    return RedirectResponse("/app/welcome-page/index.html")


def _start_public_tunnel(port: int) -> str | None:
    """
    Open an ngrok tunnel to this server and return its public https URL.

    Uses NGROK_AUTHTOKEN from src/.env, or a token already saved in ngrok's
    own config. NGROK_DOMAIN (optional) pins a free static ngrok domain so
    the link stays the same between runs.
    """
    from pyngrok import ngrok

    token = os.getenv("NGROK_AUTHTOKEN")
    if token:
        ngrok.set_auth_token(token)
    domain = (os.getenv("NGROK_DOMAIN") or "").strip()
    options = {"domain": domain} if domain else {}
    try:
        return ngrok.connect(port, "http", **options).public_url
    except Exception:
        logger.exception("Could not open the public ngrok tunnel")
        return None


if __name__ == "__main__":
    import sys
    import threading
    import webbrowser

    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    local_url = f"http://localhost:{port}"
    print(f"\n>>> Local (this machine):  {local_url}", flush=True)

    if "--public" in sys.argv:
        public_url = _start_public_tunnel(port)
        if public_url:
            print(f">>> Public (share it):     {public_url}\n", flush=True)
        else:
            print(">>> No public link: check NGROK_AUTHTOKEN in src/.env\n", flush=True)

    # --no-open wins, so the auto-start shortcut doesn't pop a browser at login.
    if "--open" in sys.argv and "--no-open" not in sys.argv:
        # Give the index a few seconds to load before the browser asks for pages.
        threading.Timer(3.0, webbrowser.open, args=(local_url,)).start()

    uvicorn.run(app, host="0.0.0.0", port=port)
