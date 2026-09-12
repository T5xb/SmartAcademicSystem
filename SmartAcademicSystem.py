"""
Gradio demo UI for the GP2 "Smart Academic Advising System" -- the RAG
module described in the GP1 report (Group M3).

This implements Use Case 2 (Ask Academic Question via Chatbot) and
Use Case 3 (Receive Source-Based Answer) end-to-end: a question comes in,
gets answered strictly from retrieved official documents, and the answer
carries real citations (document + page/article) resolved from the actual
retrieved chunks -- see src/citation.py:format_citations.

CSP scheduling and transcript parsing (also in GP1 scope) are separate,
not-yet-built modules. The UI is intentionally bare -- title and chat box
only -- since a proper front end is being built separately.

Run:
    .venv/Scripts/python.exe SmartAcademicSystem.py
It prints a local URL, plus a public one when ngrok is configured (see
README).
"""

import logging
import os
import sys

# Must be set before `import gradio`. The only network call this app should
# ever make is to the configured LLM provider, so Gradio's own phone-home
# analytics/update checks are turned off.
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

# Without this, a piped/redirected stdout is fully buffered and the URL
# below can sit unseen in the buffer instead of printing right away.
sys.stdout.reconfigure(line_buffering=True)

import gradio as gr
from dotenv import load_dotenv

load_dotenv("src/.env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gp2-chatbot")

workflow = None


def _ensure_workflow():
    """Build the RAG workflow on first use and cache it.

    Gradio's dev server can import this module more than once, and
    building the workflow is slow, so it must not happen at import time.
    A module-level cache is enough -- this app is single-process.
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


# Bare on purpose: this doubles as an API another front end can call,
# which Gradio generates from `fn`'s signature below.
demo = gr.ChatInterface(
    fn=answer,
    title="المرشد الأكاديمي الذكي",
    flagging_mode="never",
)

# Where the ngrok agent keeps its config on Windows, used as a fallback in
# case pyngrok reports a different path than the agent actually wrote to.
_DEFAULT_NGROK_CONFIG = os.path.join(
    os.getenv("LOCALAPPDATA", ""), "ngrok", "ngrok.yml"
)


def _start_ngrok_tunnel(port: int) -> str | None:
    """
    Open a public URL to our local server via ngrok, if NGROK_AUTHTOKEN is
    set in src/.env.

    Why not Gradio's own share=True: this network blocks the port its
    tunnel binary needs (it downloads fine, then fails with "Could not
    create share link"). ngrok connects out over ordinary HTTPS, which
    this network allows, so it gets through.

    Two ways to be authenticated, checked in this order:
      1. NGROK_AUTHTOKEN in src/.env (wins, and is what a fresh machine
         needs) -- free token from
         https://dashboard.ngrok.com/get-started/your-authtoken
      2. an authtoken already in ngrok's own config file, which is where
         the ngrok agent stores it after a one-time `ngrok config
         add-authtoken`. If it's there, this machine is already set up and
         .env doesn't need a copy of the token as well.

    Free-tier ngrok URLs change every run -- resend the new link each time
    you restart.
    """
    from pyngrok import conf, ngrok

    token = os.getenv("NGROK_AUTHTOKEN")
    if token:
        ngrok.set_auth_token(token)
    elif not _ngrok_config_has_token(conf.get_default().config_path):
        return None

    tunnel = ngrok.connect(port, "http")
    return tunnel.public_url


def _ngrok_config_has_token(config_path: str | None) -> bool:
    """
    Whether ngrok's own YAML config already holds a non-empty authtoken.

    Parsed with a regex rather than a YAML library because the key is
    nested (`agent: authtoken:` in config v3, top-level in v2) and this
    only needs a yes/no, not the value -- the token is never read into the
    app, it stays with the ngrok agent that owns it.
    """
    import re

    for path in filter(None, [config_path, _DEFAULT_NGROK_CONFIG]):
        try:
            with open(path, encoding="utf-8") as f:
                if re.search(r"^\s*authtoken:\s*\S+", f.read(), re.MULTILINE):
                    return True
        except OSError:
            continue
    return False


if __name__ == "__main__":
    # footer_links=[] hides Gradio's own bottom-of-page links; the API
    # endpoint still works without them.
    #
    # The port is fixed rather than auto-picked because ngrok.connect()
    # needs to know it *before* launch(), and cannot discover it after.
    port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    ngrok_url = _start_ngrok_tunnel(port)
    # share only as a fallback: if ngrok already gave us a public link,
    # don't also ask for Gradio's (which this network blocks anyway).
    #
    # prevent_thread_lock=True returns from launch() immediately so we can
    # print the URLs ourselves; block_thread() then keeps serving.
    _, local_url, share_url = demo.launch(
        footer_links=[],
        prevent_thread_lock=True,
        server_port=port,
        share=not ngrok_url,
    )
    print(f"\n>>> Local (this machine only):  {local_url}", flush=True)
    public_url = ngrok_url or share_url
    if public_url:
        print(f">>> Public (share with team):   {public_url}\n", flush=True)
    else:
        print(
            ">>> No public link this run -- set NGROK_AUTHTOKEN in src/.env "
            "(see _start_ngrok_tunnel above), or check the Gradio tunnel "
            "error/log above.\n",
            flush=True,
        )
    demo.block_thread()
