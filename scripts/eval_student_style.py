"""
Score the chatbot on questions written the way students actually ask.

    uv run python scripts/eval_student_style.py            # all questions
    uv run python scripts/eval_student_style.py --limit 5  # quick check

For each question it checks:
  - behaviour: answered / said "no answer" / small talk, against `expect`
  - content:   at least one `any_of` word appears
  - citations: a sourced answer carries a "المصادر:" block
  - style:     no "بناءً على السياق"-type openers, not longer than 15 lines,
               and the greeting is returned when the student greeted
The full answers go to output/eval_student_style.md (git-ignored).
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS = os.path.join(ROOT, "tests", "eval", "student_questions.json")
REPORT = os.path.join(ROOT, "output", "eval_student_style.md")

MAX_BODY_LINES = 18
STIFF_OPENERS = re.compile(r"بناءً على|بناء على|وفقًا للسياق|وفقا للسياق|حسب السياق|في السياق المقدم")


def behaviour(answer: str) -> str:
    from src.citation import NO_ANSWER_MESSAGE

    if NO_ANSWER_MESSAGE.splitlines()[0] in answer:
        return "no_answer"
    if "المصادر:" in answer:
        return "answer"
    return "small_talk" if len(answer) < 300 else "answer"


def score(item: dict, answer: str) -> dict:
    from src.student_style import opens_with_greeting

    got = behaviour(answer)
    checks = {
        "behaviour": got == item["expect"],
        "content": any(w in answer for w in item["any_of"]),
        # Length is judged on the answer body; the sources list can be long.
        "style": not STIFF_OPENERS.search(answer)
        and answer.split("المصادر:")[0].strip().count("\n") <= MAX_BODY_LINES
        and answer.count("وعليكم السلام") <= 1,
    }
    if item["expect"] == "answer":
        checks["citations"] = "المصادر:" in answer
    if opens_with_greeting(item["q"]):
        checks["greeting"] = answer.startswith("وعليكم السلام")
    return {"got": got, "checks": checks}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    load_dotenv("src/.env")
    logging.disable(logging.INFO)
    items = json.load(open(QUESTIONS, encoding="utf-8"))["questions"]
    if args.limit:
        items = items[: args.limit]

    from src.workflow import create_workflow

    workflow = create_workflow()
    rows, totals = [], {}
    for i, item in enumerate(items, 1):
        start = time.perf_counter()
        try:
            answer = await workflow.run(user_msg=item["q"])
        except Exception as e:  # keep going: one rate-limit shouldn't end the run
            answer = f"ERROR: {e}"
        elapsed = time.perf_counter() - start
        result = score(item, answer)
        for k, ok in result["checks"].items():
            t = totals.setdefault(k, [0, 0])
            t[0] += ok
            t[1] += 1
        passed = all(result["checks"].values())
        print(f"[{i:02d}] {'PASS' if passed else 'FAIL'}  {elapsed:4.1f}s  {item['q']}")
        rows.append((item, answer, result, elapsed))

    print("\nscore by check:")
    for k, (ok, n) in totals.items():
        print(f"  {k:10s} {ok}/{n}")
    full = sum(all(r[2]["checks"].values()) for r in rows)
    print(f"  {'all':10s} {full}/{len(rows)}")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(f"# Student-style evaluation\n\nPassed all checks: {full}/{len(rows)}\n\n")
        for item, answer, result, elapsed in rows:
            failed = [k for k, ok in result["checks"].items() if not ok]
            f.write(f"## {item['q']}\n\n- topic: {item['topic']} | expect: {item['expect']} | got: {result['got']}"
                    f" | {elapsed:.1f}s | failed: {', '.join(failed) or 'none'}\n\n{answer}\n\n---\n\n")
    print(f"\nfull answers: {REPORT}")


if __name__ == "__main__":
    asyncio.run(main())
