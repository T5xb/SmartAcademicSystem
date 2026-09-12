"""
Run the same questions through the chatbot and report answer + latency,
for whichever LLM provider is selected.

Used to produce the local-vs-hosted comparison in GP2: run it once per
provider and put the two latency columns side by side. Recorded results
are in ARCHITECTURE.md §5.

Usage:
    .venv/Scripts/python.exe scripts/bench.py                  # provider from src/.env
    .venv/Scripts/python.exe scripts/bench.py --provider ollama
    .venv/Scripts/python.exe scripts/bench.py --provider hosted "سؤالك هنا"

With no questions on the command line it uses NEXT_PUBLIC_STARTER_QUESTIONS
from src/.env, so both runs are compared on identical inputs.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("questions", nargs="*")
    parser.add_argument("--provider", choices=["hosted", "ollama"])
    args = parser.parse_args()

    load_dotenv("src/.env")
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    # Keep the report readable: the HTTP/index chatter isn't what we measure.
    logging.disable(logging.INFO)

    questions = args.questions or json.loads(
        os.getenv("NEXT_PUBLIC_STARTER_QUESTIONS", "[]")
    )
    if not questions:
        sys.exit("No questions given and NEXT_PUBLIC_STARTER_QUESTIONS is empty.")

    from src.workflow import create_workflow

    provider = os.getenv("LLM_PROVIDER") or ("hosted" if os.getenv("LLM_API_KEY") else "ollama")
    model = os.getenv("MODEL") if provider == "ollama" else os.getenv("LLM_MODEL")
    print(f"provider={provider}  model={model}  top_k={os.getenv('TOP_K')}\n")

    workflow = create_workflow()
    timings = []
    for i, question in enumerate(questions, 1):
        start = time.perf_counter()
        answer = await workflow.run(user_msg=question)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)
        print(f"[{i}] {question}\n    ({elapsed:.1f}s)\n{answer}\n{'-' * 70}")

    print(f"\nmean {sum(timings) / len(timings):.1f}s over {len(timings)} question(s)")


if __name__ == "__main__":
    asyncio.run(main())
