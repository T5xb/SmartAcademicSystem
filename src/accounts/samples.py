"""
Sample academic records, so an advisor sees a complete student profile.

The prototype has no link to the university's records yet, so a student who
hasn't imported a transcript gets a sample one: completed courses up to a
level, a GPA, earned hours, and the eligible/suggested courses the planner
computes. It is marked "source": "sample"; a real transcript the student
imports on the schedule page replaces it. Contact fields are only filled
when empty, so a student's own edits are never overwritten.
"""

import hashlib
from datetime import datetime

from . import store

# Levels completed, cumulative GPA, and courses not passed, picked per
# student from their ID so each one looks different but stays the same.
_PROFILES = [
    (2, 4.12, 0),
    (4, 3.45, 0),
    (6, 2.31, 1),
    (3, 3.80, 0),
    (5, 1.87, 2),
    (1, 4.60, 0),
]


def _pick(username: str) -> tuple[int, float, int]:
    digest = int(hashlib.sha256(username.encode("utf-8")).hexdigest(), 16)
    return _PROFILES[digest % len(_PROFILES)]


def _preset(username: str) -> tuple[int, float, int] | None:
    """The three preset students get distinct, fixed records."""
    return {
        "441000001": (2, 4.12, 0),
        "441000002": (4, 3.45, 0),
        "441000003": (6, 2.31, 1),
    }.get(username)


def sample_record(user: dict) -> dict:
    """A transcript in the same shape the PDF import produces."""
    # Imported here: the scheduling module loads the course data and solver.
    from src.scheduling.course_data import LEVEL_MAP, course_db
    from src.scheduling.service import _eligible, _suggest

    levels, gpa, failed = _preset(user["username"]) or _pick(user["username"])
    by_level = sorted(
        (c for c in course_db if LEVEL_MAP.get(c.code) and LEVEL_MAP[c.code] <= levels),
        key=lambda c: (LEVEL_MAP[c.code], c.code),
    )
    # The last courses of the highest level are the ones not passed yet.
    not_passed = [c.code for c in by_level[-failed:]] if failed else []
    completed = {c.code for c in by_level} - set(not_passed)
    hours = sum(c.credit_hours for c in course_db if c.code in completed)
    return {
        "student": {
            "name": user["name"], "id": user["username"],
            "college": "كلية علوم الحاسب والمعلومات", "major": "علوم الحاسب",
        },
        "gpa": gpa,
        "earned_hours": hours,
        "completed": sorted(completed),
        "unmapped": [],
        "not_passed": sorted(not_passed),
        "eligible": [c.code for c in _eligible(completed)],
        "suggested": _suggest(completed),
        "warnings": [],
        "parsed_courses": len(by_level),
        "parsed_at": datetime.now().isoformat(timespec="seconds"),
        "source": "sample",
    }


def ensure_sample_record(user: dict) -> bool:
    """Give a student without a transcript a sample one. True when added."""
    if user["role"] != "student":
        return False
    profile = store.get_profile(user["id"])
    if profile.get("transcript"):
        return False
    record = sample_record(user)
    levels = _preset(user["username"]) or _pick(user["username"])
    changes = {"transcript": record}
    defaults = {
        "major": "علوم الحاسب",
        "level": f"Level {min(levels[0] + 1, 8)}",
        "email": f"{user['username']}@sm.imamu.edu.sa",
        "phone": f"05{user['username'][-8:].rjust(8, '0')}",
    }
    for key, value in defaults.items():
        if not profile.get(key):
            changes[key] = value
    store.update_profile(user["id"], changes)
    return True


def seed_sample_records() -> list[str]:
    """Every student without a transcript gets a sample one (at startup)."""
    return [u["username"] for u in store.list_users("student") if ensure_sample_record(u)]
