"""
Glue between the CSP scheduler and the JSON API used by frontend/schedule-page.

The scheduler itself (csp_scheduler.py) works on dataclasses; this module turns
the course plan into plain dicts for the browser, runs the solver for a request,
and turns a transcript PDF into the student's completed courses.
"""
from dataclasses import replace
from datetime import datetime
from typing import BinaryIO, Dict, List, Optional, Set

from .code_mapping import map_transcript_codes
from .course_data import CS_ELECTIVE_POOL_CODES, LEVEL_MAP, MAX_REQUIRED_ELECTIVES, course_db
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

COURSE_BY_CODE: Dict[str, Course] = {c.code: c for c in course_db}


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
        "crn": section.section_id,
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
    targets = _target_courses(course_codes, include_closed)
    locks = {k: v for k, v in (locks or {}).items() if k in {c.code for c in targets}}
    for code, section_id in locks.items():
        if section_id not in {s.section_id for s in COURSE_BY_CODE[code].available_sections}:
            raise ScheduleRequestError(f"Course {code} has no section {section_id}")

    result = {"schedules": [], "errors": [], "failure_reason": None, "truncated": False}
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
        return result

    scheduler = StudentCSPScheduler(
        student, pinned_sections=locks, start_time=time_from, end_time=time_to,
        preferred_instructors=preferred_instructors, min_days_off=min_days_off,
    )
    scheduler.solve_all(limit=limit)
    schedules = scheduler.get_all_schedules()
    if not schedules:
        result["failure_reason"] = scheduler.failure_reason
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
