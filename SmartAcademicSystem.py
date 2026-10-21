"""
Run:
    .venv/Scripts/python.exe SmartAcademicSystem.py
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

demo = gr.ChatInterface(
    fn=answer,
    title="المرشد الأكاديمي الذكي",
    flagging_mode="never",
)

_DEFAULT_NGROK_CONFIG = os.path.join(
    os.getenv("LOCALAPPDATA", ""), "ngrok", "ngrok.yml"
)


def _start_ngrok_tunnel(port: int) -> str | None:
   
    from pyngrok import conf, ngrok

    token = os.getenv("NGROK_AUTHTOKEN")
    if token:
        ngrok.set_auth_token(token)
    elif not _ngrok_config_has_token(conf.get_default().config_path):
        return None

    tunnel = ngrok.connect(port, "http")
    return tunnel.public_url


def _ngrok_config_has_token(config_path: str | None) -> bool:

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
  
    port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    ngrok_url = _start_ngrok_tunnel(port)
    
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
