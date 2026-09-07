"""
Gradio demo UI for the GP2 "Smart Academic Advising System" -- the RAG
module described in the GP1 report (Group M3).

This implements Use Case 2 (Ask Academic Question via Chatbot) and
Use Case 3 (Receive Source-Based Answer) end-to-end: a question comes in,
gets answered strictly from retrieved official documents, and the answer
carries real citations (document + page/article) resolved from the actual
retrieved chunks -- see src/citation.py:format_citations.

CSP-based schedule generation and transcript parsing (also in the GP1
scope) are separate, not-yet-built modules -- this only covers the RAG
chatbot. The UI here is intentionally bare (title + chat box only, no
extra panels) since it's just for quick testing while a separate real
front end is being built elsewhere.

Run:
    .venv/Scripts/python.exe SmartAcademicSystem.py
Then open the local URL Gradio prints (defaults to http://127.0.0.1:7860).
"""

import logging
import os
import sys

# Must be set before `import gradio` -- this project runs fully offline
# (Ollama only, no cloud calls), so Gradio's phone-home analytics/update
# checks are turned off rather than left as a silent exception to that.
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

# Some ways of launching this script (some IDE "run" buttons, output
# redirected to a file/pipe) fully buffer stdout instead of flushing per
# line, so Gradio's own "Running on local URL: ..." print can sit unseen
# in a buffer for a while (or until the process exits) instead of showing
# up right away. Force line-buffering so it always appears immediately.
sys.stdout.reconfigure(line_buffering=True)

import gradio as gr
from dotenv import load_dotenv

load_dotenv("src/.env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gp2-chatbot")

workflow = None


def _ensure_workflow():
    """Build the RAG workflow lazily, on first use, and cache it.

    Gradio's dev server can import this module more than once; building
    the (fairly slow) index/workflow eagerly at import time would do that
    work repeatedly. A plain module-level cache is enough here since this
    app is single-process.
    """
    global workflow
    if workflow is None:
        from src.workflow import create_workflow

        logger.info("Loading index and building workflow...")
        workflow = create_workflow()
        logger.info("Ready.")
    return workflow


async def answer(message: str, history: list) -> str:
    wf = _ensure_workflow()
    return await wf.run(user_msg=message)


# Bare-bones on purpose: just the title and the chat box, no status panel,
# description, examples, or flagging (like/dislike) buttons -- this is
# meant for quick manual testing plus, more importantly, as an API another
# front end can call directly (see the README for the raw HTTP call shape;
# Gradio auto-generates that API from `fn`'s signature below).
demo = gr.ChatInterface(
    fn=answer,
    title="المرشد الأكاديمي الذكي",
    flagging_mode="never",
)

if __name__ == "__main__":
    # footer_links=[] hides Gradio's bottom-of-page links (API docs,
    # branding, settings, run history) -- this only hides those links, the
    # API endpoint itself (see README) still works with them gone.
    #
    # share=True (temporary public URL via Gradio's tunneling service)
    # was attempted but stalled downloading its tunnel binary -- shelved
    # for later rather than blocking on it. Local-only for now.
    # prevent_thread_lock=True makes launch() return right after the server
    # starts (instead of blocking inside launch() until Ctrl+C), so we can
    # print the URL ourselves guaranteed, then block_thread() afterwards to
    # keep the process alive and serving.
    _, local_url, _ = demo.launch(footer_links=[], prevent_thread_lock=True)
    print(f"\n>>> Open this in your browser: {local_url}\n", flush=True)
    demo.block_thread()
