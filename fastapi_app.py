
import json
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv("src/.env")

# Imported after load_dotenv() so DATA_DIR picks up an .env override, if any.
from src.index import DATA_DIR  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gp2-chatbot")

workflow = None
# The chat page is static once rendered (starter questions come from .env,
# fixed for the life of the process), so render it once at startup instead
# of on every GET /.
rendered_html = None
starter_questions: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global workflow, rendered_html, starter_questions
    from src.workflow import create_workflow

    logger.info("Loading index and building workflow...")
    workflow = create_workflow()

    starter_raw = os.getenv("NEXT_PUBLIC_STARTER_QUESTIONS", "[]")
    try:
        starter_questions = json.loads(starter_raw)
    except json.JSONDecodeError:
        starter_questions = []
    starters_json = json.dumps(starter_questions, ensure_ascii=False)
    rendered_html = HTML_PAGE.replace("__STARTER_QUESTIONS__", starters_json)

    logger.info("Ready.")
    yield


app = FastAPI(title="GP2 RAG Chatbot", lifespan=lifespan)

# The GP2 front end (chatbot-page) is opened from another origin — a file://
# page, another port, or an ngrok URL — so the browser needs CORS headers.
# Override with a comma-separated CORS_ORIGINS list to lock this down.
cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Serve any files the user drops in DATA_DIR (optional, handy for debugging)
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    response: str


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
        response = await workflow.run(user_msg=message)
    except Exception:
        # Retrieval or the LLM provider failed (rate limit, network, DB);
        # the front end shows this detail in its error card.
        logger.exception("Chat request failed")
        raise HTTPException(
            status_code=502,
            detail="The advising service could not generate an answer right now. Please try again.",
        )
    return ChatResponse(response=response)


@app.get("/", response_class=HTMLResponse)
async def index():
    return rendered_html


HTML_PAGE = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8" />
<title>المرشد الأكاديمي الذكي</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root { color-scheme: light dark; }
  body {
    margin: 0; font-family: 'Segoe UI', Tahoma, system-ui, sans-serif; background: #0f1115; color: #e8e8ec;
    display: flex; flex-direction: column; height: 100vh;
  }
  header { padding: 16px 20px; border-bottom: 1px solid #22252b; }
  header h1 { margin: 0; font-size: 18px; }
  header p { margin: 4px 0 0; font-size: 13px; color: #9aa0ab; }
  #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
  .msg { max-width: 70%; padding: 10px 14px; border-radius: 12px; line-height: 1.7; white-space: pre-wrap; }
  .user { align-self: flex-end; background: #2b6cff; color: white; }
  .bot { align-self: flex-start; background: #1c1f26; border: 1px solid #262a33; }
  .bot.pending { color: #9aa0ab; font-style: italic; }
  #starters { display: flex; flex-wrap: wrap; gap: 8px; padding: 0 20px 16px; }
  .starter-btn {
    padding: 8px 14px; border-radius: 999px; border: 1px solid #2a2e37; background: #171a20;
    color: #c7cbd4; font-size: 13px; cursor: pointer;
  }
  .starter-btn:hover { background: #1c2029; border-color: #2b6cff; }
  form { display: flex; gap: 10px; padding: 16px 20px; border-top: 1px solid #22252b; }
  input { flex: 1; padding: 12px 14px; border-radius: 8px; border: 1px solid #2a2e37; background: #14161b; color: #e8e8ec; font-size: 14px; }
  input:focus { outline: 2px solid #2b6cff; }
  button { padding: 12px 18px; border-radius: 8px; border: none; background: #2b6cff; color: white; font-size: 14px; cursor: pointer; }
  button:disabled { opacity: 0.5; cursor: default; }
</style>
</head>
<body>
  <header>
    <h1>المرشد الأكاديمي الذكي</h1>
    <p>اسأل عن الأنظمة واللوائح الأكاديمية بجامعة الإمام &mdash; كل إجابة مبنية على الوثائق الرسمية للجامعة، مع ذكر المصدر والصفحة.</p>
  </header>
  <div id="chat"></div>
  <div id="starters"></div>
  <form id="form">
    <input id="input" autocomplete="off" placeholder="اكتب سؤالك الأكاديمي هنا..." />
    <button id="send" type="submit">إرسال</button>
  </form>

<script>
const chatEl = document.getElementById('chat');
const startersEl = document.getElementById('starters');
const form = document.getElementById('form');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');

const starterQuestions = __STARTER_QUESTIONS__;
starterQuestions.forEach(q => {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'starter-btn';
  btn.textContent = q;
  btn.addEventListener('click', () => {
    input.value = q;
    form.requestSubmit();
  });
  startersEl.appendChild(btn);
});

function addMsg(role, text, pending=false) {
  const div = document.createElement('div');
  div.className = 'msg ' + (role === 'user' ? 'user' : 'bot') + (pending ? ' pending' : '');
  div.textContent = text;
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = '';
  sendBtn.disabled = true;
  startersEl.hidden = true;
  addMsg('user', message);
  const pendingEl = addMsg('bot', 'جارِ البحث في الوثائق...', true);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : res.status);
    pendingEl.textContent = data.response;
    pendingEl.classList.remove('pending');
  } catch (err) {
    pendingEl.textContent = 'حدث خطأ: ' + err;
    pendingEl.classList.remove('pending');
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
