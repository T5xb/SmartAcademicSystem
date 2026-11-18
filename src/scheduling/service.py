"""
Glue between the CSP scheduler and the JSON API used by frontend/schedule-page.

The scheduler itself (csp_scheduler.py) works on dataclasses; this module turns
the course plan into plain dicts for the browser, runs the solver for a request,
and turns a transcript PDF into the student's completed courses.
"""
import logging
import threading
import time
from dataclasses import replace
from itertools import combinations
from datetime import datetime
from typing import BinaryIO, Dict, List, Optional, Set

from .code_mapping import map_transcript_codes
from . import offerings
from .course_data import CS_ELECTIVE_POOL_CODES, LEVEL_MAP, MAX_REQUIRED_ELECTIVES
from .csp_scheduler import StudentCSPScheduler, evaluate_schedule
from .models import Course, CourseSection, Student, parse_exam_datetime
from .transcript_parser import parse_transcript
from .validation import validate_course_selection

# Column order of the timetable in the web page (Sunday..Thursday).
DAY_INDEX = {"الأحد": 0, "الاثنين": 1, "الثلاثاء": 2, "الأربعاء": 3, "الخميس": 4}

COLORS = [
    "#16d076", "#a855f7", "#3b82f6", "#f97316", "#06b6d4", "#ec4899", "#eab308",
    "#14b8a6", "#6366f1", "#ef4444", "#84cc16", "#f43f5e", "#0ea5e9", "#d946ef",
]

DEFAULT_MAX_CREDITS = 18
MAX_SCHEDULES = 300
SUGGESTED_CREDITS = 18

logger = logging.getLogger("gp2-scheduler")

# ---------------------------------------------------------------- offered courses
# The courses, sections, times and seats come from the admin's Excel file
# (src/scheduling/offerings.py), saved in the shared database. Until one is
# uploaded, the built-in plan with made-up CRNs and seats is used. Another
# server on the same database picks up a new file within REFRESH_SECONDS.

REFRESH_SECONDS = 20
DEFAULT_OFFERINGS = offerings.default_offerings()

course_db: List[Course] = []
COURSE_BY_CODE: Dict[str, Course] = {}
_source = {"raw": None, "checked": 0.0, "updated_at": None, "updated_by": None}
_refresh_lock = threading.Lock()


def _apply(plain: List[dict], updated_at=None, updated_by=None) -> None:
    global course_db, COURSE_BY_CODE
    courses = offerings.to_courses(plain)
    course_db, COURSE_BY_CODE = courses, {c.code: c for c in courses}
    _source.update(updated_at=updated_at, updated_by=updated_by)


def use_defaults() -> None:
    """Back to the built-in data, and read the database again on next use."""
    with _refresh_lock:
        _apply(DEFAULT_OFFERINGS)
        _source.update(raw=None, checked=0.0)


def refresh(force: bool = False) -> None:
    if not force and time.monotonic() - _source["checked"] < REFRESH_SECONDS:
        return
    with _refresh_lock:
        if not force and time.monotonic() - _source["checked"] < REFRESH_SECONDS:
            return
        try:
            saved = offerings.load_saved()
        except Exception:
            # Database unreachable: keep whatever is loaded now.
            logger.warning("Could not read the course offerings; keeping the current ones", exc_info=True)
            saved = _source["raw"]
        _source["checked"] = time.monotonic()
        if saved is _source["raw"] or (saved and saved == _source["raw"]):
            return
        _source["raw"] = saved
        if saved:
            _apply(saved["courses"], saved.get("updated_at"), saved.get("updated_by"))
        else:
            _apply(DEFAULT_OFFERINGS)


def current_offerings() -> List[dict]:
    """The offered courses as plain data (what the Excel file holds)."""
    refresh()
    return _source["raw"]["courses"] if _source["raw"] else DEFAULT_OFFERINGS


def source_info() -> dict:
    refresh()
    return {"custom": _source["raw"] is not None, "updated_at": _source["updated_at"],
            "updated_by": _source["updated_by"]}


_apply(DEFAULT_OFFERINGS)


class ScheduleRequestError(ValueError):
    """The request names courses or sections that are not in the plan."""


# ---------------------------------------------------------------- catalog

def _exam_json(course: Course) -> Optional[dict]:
    exam = parse_exam_datetime(course.final_exam)
    if exam is None:
        return None
    return {"date": exam.strftime("%Y-%m-%d"), "start": exam.hour * 60 + exam.minute}


def _section_json(section: CourseSection) -> dict:
    meetings = [
        {"day": DAY_INDEX[day], "start": ts.start_minutes(), "end": ts.end_minutes(),
         "room": "", "type": "Lecture"}
        for ts in section.time_slots for day in ts.days if day in DAY_INDEX
    ]
    return {
        "id": section.section_id,
        "crn": section.crn or section.section_id,
        "capacity": section.capacity,
        "enrolled": section.enrolled,
        "instructor": "" if section.doctor_name == "غير محدد" else section.doctor_name,
        "meetings": meetings,
    }


def _course_json(index: int, course: Course) -> dict:
    return {
        "code": course.code,
        "name": course.name,
        "short": course.name,
        "credits": course.credit_hours,
        "color": COLORS[index % len(COLORS)],
        "level": LEVEL_MAP.get(course.code),
        "elective": course.code in CS_ELECTIVE_POOL_CODES,
        "prerequisites": [
            {"code": p, "name": COURSE_BY_CODE[p].name if p in COURSE_BY_CODE else p}
            for p in course.prerequisites
        ],
        "exam": _exam_json(course),
        "sections": [_section_json(s) for s in course.available_sections],
    }


def catalog() -> dict:
    refresh()
    return {
        "courses": [_course_json(i, c) for i, c in enumerate(course_db)],
        "max_electives": MAX_REQUIRED_ELECTIVES,
        "default_max_credits": DEFAULT_MAX_CREDITS,
    }


# ---------------------------------------------------------------- scheduling

def _target_courses(codes: List[str], include_closed: bool) -> List[Course]:
    unknown = [c for c in codes if c not in COURSE_BY_CODE]
    if unknown:
        raise ScheduleRequestError(f"Unknown course code(s): {', '.join(unknown)}")
    courses = [COURSE_BY_CODE[c] for c in dict.fromkeys(codes)]
    if include_closed:
        # "Include closed sections" = ignore the seat limit (constraint H5).
        courses = [
            replace(c, available_sections=[replace(s, capacity=None) for s in c.available_sections])
            for c in courses
        ]
    return courses


# ---------------------------------------------------------------- why nothing fits
# Each problem is {"kind": ..., plus the names/values the page needs to write
# the message and the fix}. The page translates them, so they stay plain data.

def _selection_problems(targets: List[Course], completed: List[str], max_credits: int) -> List[dict]:
    problems = []
    for course in targets:
        for code in course.prerequisites:
            if code not in completed:
                prereq = COURSE_BY_CODE.get(code)
                problems.append({"kind": "prereq", "course": course.name, "code": course.code,
                                 "prereq": prereq.name if prereq else code})
    total = sum(c.credit_hours for c in targets)
    if total > max_credits:
        problems.append({"kind": "credits", "total": total, "max": max_credits})
    electives = [c for c in targets if c.code in CS_ELECTIVE_POOL_CODES]
    if len(electives) > MAX_REQUIRED_ELECTIVES:
        problems.append({"kind": "electives", "n": len(electives), "max": MAX_REQUIRED_ELECTIVES,
                         "names": [c.name for c in electives]})
    return problems


def _schedule_problems(targets: List[Course], scheduler: StudentCSPScheduler, student: Student,
                       locks: Dict[str, str], time_from: str, time_to: str,
                       min_days_off: int) -> List[dict]:
    window = {"from": time_from, "to": time_to}

    # 1) A course with no usable section at all, before any clash is looked at.
    problems = []
    for course in targets:
        if scheduler.domains[course.code]:
            continue
        base = {"course": course.name, "code": course.code}
        if course.code in locks:
            section = next(s for s in course.available_sections if s.section_id == locks[course.code])
            kind = "locked_full" if not section.has_open_seats() else "locked_time"
            problems.append({"kind": kind, "section": section.section_id, **base, **window})
        elif not any(s.has_open_seats() for s in course.available_sections):
            problems.append({"kind": "all_full", **base})
        else:
            problems.append({"kind": "outside_time", **base, **window})
    if problems:
        return problems

    # 2) Two courses that can never sit together: same final exam, or every
    #    section of one clashes with every section of the other.
    for a, b in combinations(targets, 2):
        pair = {"a": a.name, "b": b.name, "codes": [a.code, b.code]}
        if scheduler._exam_clash(a, b):
            problems.append({"kind": "exam_clash", "exam": a.final_exam, **pair})
        elif all(scheduler._is_conflict(x, y)
                 for x in scheduler.domains[a.code] for y in scheduler.domains[b.code]):
            locked = [f"{c.name} ({locks[c.code]})" for c in (a, b) if c.code in locks]
            problems.append({"kind": "time_clash", "locked": locked, **pair})
    if problems:
        return problems

    # 3) It fits, just not with that many days off.
    if min_days_off > 0:
        relaxed = StudentCSPScheduler(student, pinned_sections=locks,
                                      start_time=time_from, end_time=time_to)
        if relaxed.solve_all(limit=1):
            return [{"kind": "days_off", "n": min_days_off}]

    # 4) Three or more courses that clash only together.
    return [{"kind": "no_combination", "names": [c.name for c in targets],
             "locked": [f"{c.name} ({locks[c.code]})" for c in targets if c.code in locks]}]


def generate(
    course_codes: List[str],
    locks: Optional[Dict[str, str]] = None,
    time_from: str = "00:00",
    time_to: str = "23:59",
    min_days_off: int = 0,
    include_closed: bool = False,
    completed_courses: Optional[List[str]] = None,
    max_credit_hours: int = DEFAULT_MAX_CREDITS,
    prefer_morning: bool = False,
    preferred_instructors: Optional[Dict[str, str]] = None,
    limit: int = MAX_SCHEDULES,
) -> dict:
    """
    Validates the selection, runs the CSP and returns the schedules best-first.
    Prerequisites are only checked when completed_courses is given (a transcript
    was imported); without it the student's history is unknown.
    """
    refresh()
    targets = _target_courses(course_codes, include_closed)
    locks = {k: v for k, v in (locks or {}).items() if k in {c.code for c in targets}}
    for code, section_id in locks.items():
        if section_id not in {s.section_id for s in COURSE_BY_CODE[code].available_sections}:
            raise ScheduleRequestError(f"Course {code} has no section {section_id}")

    result = {"schedules": [], "errors": [], "failure_reason": None, "truncated": False,
              "problems": []}
    if not targets:
        return result

    if completed_courses is None:
        # No transcript: treat every prerequisite as met so only the
        # credit-hour and elective checks apply.
        completed_courses = [p for c in targets for p in c.prerequisites]
    student = Student("web", completed_courses, targets)
    errors = validate_course_selection(
        targets, student, course_db, max_credit_hours,
        elective_pool_codes=CS_ELECTIVE_POOL_CODES, max_electives=MAX_REQUIRED_ELECTIVES,
    )
    if errors:
        result["errors"] = errors
        result["problems"] = _selection_problems(targets, student.completed_courses, max_credit_hours)
        return result

    scheduler = StudentCSPScheduler(
        student, pinned_sections=locks, start_time=time_from, end_time=time_to,
        preferred_instructors=preferred_instructors, min_days_off=min_days_off,
    )
    scheduler.solve_all(limit=limit)
    schedules = scheduler.get_all_schedules()
    if not schedules:
        result["failure_reason"] = scheduler.failure_reason
        result["problems"] = _schedule_problems(
            targets, scheduler, student, locks, time_from, time_to, min_days_off)
        return result

    scored = [
        (evaluate_schedule(s, prefer_morning=prefer_morning,
                           preferred_instructors=preferred_instructors), s)
        for s in schedules
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    result["truncated"] = len(schedules) >= limit
    result["schedules"] = [
        {"score": round(score, 1),
         "picks": [{"code": c.code, "section": sched[c.code].section_id} for c in targets]}
        for score, sched in scored
    ]
    return result


# ---------------------------------------------------------------- transcript

def _eligible(completed: Set[str]) -> List[Course]:
    return [
        c for c in course_db
        if c.code not in completed and all(p in completed for p in c.prerequisites)
    ]


def _suggest(completed: Set[str], max_credits: int = SUGGESTED_CREDITS) -> List[str]:
    """Lowest-level required courses the student can take, kept clash-free."""
    candidates = sorted(
        (c for c in _eligible(completed) if c.code in LEVEL_MAP),
        key=lambda c: (LEVEL_MAP[c.code], c.code),
    )
    picked: List[Course] = []
    credits = 0
    for course in candidates:
        if credits + course.credit_hours > max_credits:
            continue
        trial = picked + [course]
        scheduler = StudentCSPScheduler(Student("web", list(completed), trial))
        if scheduler.solve_all(limit=1):
            picked = trial
            credits += course.credit_hours
    return [c.code for c in picked]


def import_transcript(pdf: BinaryIO) -> dict:
    refresh()
    data = parse_transcript(pdf)
    completed, unmapped = map_transcript_codes(data.completed_course_codes())
    return {
        "student": {
            "name": data.student_name, "id": data.student_id,
            "college": data.college, "major": data.major,
        },
        "gpa": data.cumulative_gpa,
        "earned_hours": data.cumulative_earned_hours,
        "completed": sorted(completed),
        "unmapped": sorted(unmapped),
        "not_passed": sorted(data.failed_or_withdrawn_course_codes()),
        "eligible": [c.code for c in _eligible(completed)],
        "suggested": _suggest(completed),
        "warnings": data.parse_warnings[:20],
        "parsed_courses": len(data.courses),
        "parsed_at": datetime.now().isoformat(timespec="seconds"),
    }
