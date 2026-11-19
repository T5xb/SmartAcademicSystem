# -*- coding: utf-8 -*-
"""
The offered courses and sections (times, instructors, CRNs, seats), editable
by the admin as an Excel file.

- Built-in data: the study plan in course_data.py, with made-up CRNs and seat
  numbers (`default_offerings`). Used until the admin uploads a file.
- The admin downloads the current data as .xlsx (`to_excel`), edits it in
  Excel and uploads it back (`parse_excel`). Every row is checked first; the
  file is only saved when it has no problems.
- The saved data lives in the shared database (sas_meta), so every server on
  the team's database shows the same seats. A section is closed when its
  taken seats reach its seat count; the schedule page then won't pick it.

Plain data here is a list of course dicts:
    {"code", "name", "credits", "prerequisites": [...], "final_exam",
     "sections": [{"id", "crn", "instructor", "capacity", "enrolled",
                   "meetings": [{"days": [...], "start": "HH:MM", "end": "HH:MM"}]}]}
"""
import base64
import io
import json
import re
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import (
    EXAM_DATETIME_FORMAT, NO_EXAM_SENTINELS, Course, CourseSection, TimeSlot, parse_exam_datetime,
)

META_KEY = "course_offerings"
# The Excel file itself, as last uploaded (base64), so downloads give that file.
FILE_KEY = "course_offerings_file"
# The file for the built-in data, kept in the project (made by default_offerings()).
DEFAULT_FILE = Path(__file__).with_name("course_offerings.xlsx")

DAYS = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس"]
_DAY_ALIASES = {
    "الأحد": 0, "الاحد": 0, "أحد": 0, "احد": 0, "sun": 0, "sunday": 0,
    "الاثنين": 1, "الإثنين": 1, "اثنين": 1, "إثنين": 1, "mon": 1, "monday": 1,
    "الثلاثاء": 2, "ثلاثاء": 2, "tue": 2, "tues": 2, "tuesday": 2,
    "الأربعاء": 3, "الاربعاء": 3, "أربعاء": 3, "اربعاء": 3, "wed": 3, "wednesday": 3,
    "الخميس": 4, "خميس": 4, "thu": 4, "thur": 4, "thurs": 4, "thursday": 4,
}

# The schedule page draws 08:00 to 24:00.
EARLIEST = 8 * 60
LATEST = 24 * 60

NO_EXAM = "بدون اختبار"
UNKNOWN = "غير محدد"

# (key, Arabic header, other accepted headers)
COLUMNS = [
    ("code", "رمز المقرر", ["course code", "code"]),
    ("name", "اسم المقرر", ["course name", "name"]),
    ("credits", "الساعات", ["الساعات المعتمدة", "credits", "credit hours"]),
    ("prerequisites", "المتطلبات السابقة", ["prerequisites"]),
    ("final_exam", "الاختبار النهائي", ["final exam"]),
    ("section", "الشعبة", ["section"]),
    ("crn", "الرقم المرجعي (CRN)", ["الرقم المرجعي", "crn"]),
    ("days", "الأيام", ["days"]),
    ("start", "من", ["البداية", "start"]),
    ("end", "إلى", ["النهاية", "end"]),
    ("instructor", "اسم الدكتور", ["الدكتور", "المحاضر", "instructor"]),
    ("capacity", "عدد المقاعد", ["المقاعد", "capacity", "seats"]),
    ("enrolled", "المقاعد المأخوذة", ["المسجلون", "enrolled", "taken"]),
]
REMAINING_HEADER = "المقاعد المتبقية"   # a formula column, only for reading
REQUIRED_COLUMNS = {"code", "name", "credits", "section", "crn", "days", "start", "end"}
SHEET_NAME = "المقررات"
MAX_ROWS = 2000


class OfferingsError(ValueError):
    """The file can't be read at all (not an Excel file, no header row...)."""


# ---------------------------------------------------------------- built-in data

# Lecture times for the extra sections of the built-in data (days, start, end).
EXTRA_SLOTS = [
    (["الأحد", "الثلاثاء"], "08:00", "09:15"),
    (["الاثنين", "الأربعاء"], "10:00", "11:15"),
    (["الاثنين", "الأربعاء"], "08:00", "09:15"),
    (["الأحد", "الثلاثاء"], "10:00", "11:15"),
    (["الأحد", "الثلاثاء"], "11:30", "12:45"),
    (["الاثنين", "الأربعاء"], "11:30", "12:45"),
    (["الأحد", "الثلاثاء"], "13:00", "14:15"),
    (["الاثنين", "الأربعاء"], "13:00", "14:15"),
    (["الأحد", "الثلاثاء"], "14:30", "15:45"),
    (["الاثنين", "الأربعاء"], "14:30", "15:45"),
    (["الخميس"], "08:00", "11:00"),
    (["الخميس"], "12:00", "15:00"),
]


def _stable(text: str) -> int:
    """A number from the text that is the same on every run (unlike hash())."""
    import hashlib

    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _section_count(code: str, current: int) -> int:
    """2, 3 or 4 sections per course, never fewer than the plan has."""
    return max(current, (2, 3, 2, 4, 3)[_stable(code) % 5])


def default_offerings() -> List[dict]:
    """
    The study plan in course_data.py, with made-up CRNs and seats. Every
    course gets 2 to 4 sections: the plan's own sections first (same times
    and doctors), then extra ones at other times with other doctors.
    """
    from .course_data import course_db

    doctors = sorted({
        s.doctor_name for c in course_db for s in c.available_sections
        if s.doctor_name.startswith("د.")
    })
    courses = []
    number = 0

    def seats(section: dict) -> dict:
        nonlocal number
        number += 1
        capacity = (30, 35, 40, 45)[number % 4]
        # Made-up but stable: between about a third and nine tenths taken.
        enrolled = capacity * (3 + (number * 7) % 7) // 10
        section.update(crn=str(40000 + number * 7 + (number % 3)), capacity=capacity,
                       enrolled=min(enrolled, capacity - 1))
        return section

    # The plan's own sections first, numbered as before, so their CRNs and
    # seats stay the same; the extra sections are numbered after them.
    for course in course_db:
        courses.append({
            "code": course.code,
            "name": course.name,
            "credits": course.credit_hours,
            "prerequisites": list(course.prerequisites),
            "final_exam": course.final_exam,
            "sections": [
                seats({
                    "id": section.section_id,
                    "instructor": "" if section.doctor_name == UNKNOWN else section.doctor_name,
                    "meetings": [
                        {"days": list(ts.days), "start": ts.start_time, "end": ts.end_time}
                        for ts in section.time_slots
                    ],
                })
                for section in course.available_sections
            ],
        })
    for course in courses:
        sections = course["sections"]
        wanted = _section_count(course["code"], len(sections))
        seed = _stable(course["code"])
        known_doctor = any(s["instructor"] for s in sections)
        for k in range(len(EXTRA_SLOTS)):
            if len(sections) >= wanted:
                break
            days, start, end = EXTRA_SLOTS[(seed + k * 5) % len(EXTRA_SLOTS)]
            meeting = {"days": list(days), "start": start, "end": end}
            if any(_overlaps(meeting, m) for s in sections for m in s["meetings"]):
                continue
            taken = {s["instructor"] for s in sections}
            free = [d for d in doctors if d not in taken]
            doctor = free[(seed + len(sections)) % len(free)] if known_doctor and free else ""
            sections.append(seats({
                "id": f"{sections[0]['id']}-{len(sections) + 1}",
                "instructor": doctor,
                "meetings": [meeting],
            }))
    return courses


# ---------------------------------------------------------------- plain data -> dataclasses

def to_courses(offerings: List[dict]) -> List[Course]:
    """Course/CourseSection objects for the scheduler. Each distinct
    (days, start, end) gets its own TimeSlot index."""
    slots: Dict[Tuple, TimeSlot] = {}

    def slot(meeting: dict) -> TimeSlot:
        key = (tuple(meeting["days"]), meeting["start"], meeting["end"])
        if key not in slots:
            label = f"{'/'.join(meeting['days'])} {meeting['start']}-{meeting['end']}"
            slots[key] = TimeSlot(len(slots) + 1, meeting["start"], meeting["end"], label,
                                  days=list(meeting["days"]))
        return slots[key]

    courses = []
    for c in offerings:
        sections = [
            CourseSection(
                s["id"], c["code"], [slot(m) for m in s["meetings"]],
                s.get("instructor") or UNKNOWN,
                capacity=s.get("capacity"), enrolled=s.get("enrolled") or 0,
                crn=s.get("crn") or s["id"],
            )
            for s in c["sections"]
        ]
        courses.append(Course(c["code"], c["name"], c["credits"], list(c.get("prerequisites") or []),
                              sections, final_exam=c.get("final_exam") or UNKNOWN))
    return courses


# ---------------------------------------------------------------- Excel out

def to_excel(offerings: List[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME
    ws.sheet_view.rightToLeft = True

    headers = [h for _, h, _ in COLUMNS] + [REMAINING_HEADER]
    ws.append(headers)
    head_fill = PatternFill("solid", fgColor="0B6E4F")
    thin = Side(style="thin", color="C8D3CD")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.cell(1, len(headers)).fill = PatternFill("solid", fgColor="6B7280")

    cap_col = get_column_letter(len(COLUMNS) - 1)
    enr_col = get_column_letter(len(COLUMNS))
    full_fill = PatternFill("solid", fgColor="FDE2E2")
    shade = PatternFill("solid", fgColor="F3F7F5")

    row = 1
    for ci, c in enumerate(offerings):
        for s in c["sections"]:
            for mi, m in enumerate(s["meetings"] or [{"days": [], "start": "", "end": ""}]):
                row += 1
                first = mi == 0
                ws.append([
                    c["code"], c["name"], c["credits"],
                    "، ".join(c.get("prerequisites") or []),
                    c.get("final_exam") or "",
                    s["id"],
                    s["crn"] if first else "",
                    "/".join(m["days"]), m["start"], m["end"],
                    (s.get("instructor") or "") if first else "",
                    s.get("capacity") if first else None,
                    (s.get("enrolled") or 0) if first else None,
                    f'=IF({cap_col}{row}="","",{cap_col}{row}-{enr_col}{row})' if first else None,
                ])
                closed = first and s.get("capacity") is not None and (s.get("enrolled") or 0) >= s["capacity"]
                for cell in ws[row]:
                    cell.border = Border(bottom=thin)
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    if closed:
                        cell.fill = full_fill
                    elif ci % 2:
                        cell.fill = shade
                ws.cell(row, 2).alignment = Alignment(horizontal="right", vertical="center")
                ws.cell(row, 7).number_format = "@"
                ws.cell(row, 9).number_format = "@"
                ws.cell(row, 10).number_format = "@"

    widths = [12, 32, 9, 20, 22, 9, 16, 18, 8, 8, 24, 12, 15, 15]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(row, 2)}"

    help_ws = wb.create_sheet("طريقة التعديل")
    help_ws.sheet_view.rightToLeft = True
    help_ws.column_dimensions["A"].width = 24
    help_ws.column_dimensions["B"].width = 90
    lines = [
        ("طريقة التعديل", ""),
        ("", "عدّل ورقة «المقررات» ثم ارفع الملف من صفحة الأدمن (تبويب جدول المقررات). تتحدث صفحة الجداول مباشرة."),
        ("صف لكل شعبة", "كل صف شعبة واحدة. لشعبة لها أوقات مختلفة (مثل محاضرة + معمل) أضف صفًا آخر بنفس رمز المقرر والشعبة، واكتب فيه الأيام والوقت فقط."),
        ("إقفال شعبة", "اجعل «المقاعد المأخوذة» مساوية لـ«عدد المقاعد» (أو اجعل عدد المقاعد 0). تظهر الشعبة «ممتلئة» ولا يختارها الطالب."),
        ("مقاعد بلا حد", "اترك «عدد المقاعد» فارغًا."),
        ("الأيام", "الأحد، الاثنين، الثلاثاء، الأربعاء، الخميس — افصل بينها بـ / مثل: الأحد/الثلاثاء"),
        ("الوقت", "بنظام 24 ساعة مثل 08:00 و 13:30، بين 08:00 و 24:00."),
        ("الاختبار النهائي", "بالشكل 15-12-2026 08:00 AM، أو «بدون اختبار»، أو اتركه فارغًا إذا لم يحدد."),
        ("المتطلبات السابقة", "رموز المقررات مفصولة بفاصلة، مثل: عال 1140، عال 1241. يجب أن تكون موجودة في الملف."),
        ("الرقم المرجعي", "أرقام فقط، ولا يتكرر بين شعبتين."),
        ("المقاعد المتبقية", "تُحسب تلقائيًا، ولا تُقرأ عند الرفع."),
        ("حذف أو إضافة", "حذف صفوف مقرر يزيله من صفحة الجداول، وإضافة صفوف جديدة تضيف مقررًا أو شعبة."),
    ]
    for a, b in lines:
        help_ws.append([a, b])
    help_ws["A1"].font = Font(bold=True, size=14)
    for r in range(3, len(lines) + 1):
        help_ws.cell(r, 1).font = Font(bold=True)
        help_ws.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------- Excel in

def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r"\s+", " ", str(value)).strip()


def _int(value) -> Optional[int]:
    """None for an empty cell; raises ValueError for anything not a whole number >= 0."""
    text = _text(value)
    if not text:
        return None
    number = float(text)
    if not number.is_integer() or number < 0:
        raise ValueError(text)
    return int(number)


def _time(value) -> Optional[str]:
    """'HH:MM' from an Excel time, a datetime, a day fraction or text like 8:00 / 1:30 PM."""
    if value is None or _text(value) == "":
        return None
    if isinstance(value, datetime):
        value = value.time()
    if isinstance(value, dtime):
        return f"{value.hour:02d}:{value.minute:02d}"
    if isinstance(value, (int, float)) and 0 <= value <= 1:
        minutes = round(value * 24 * 60)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
    text = _text(value).upper().replace("ص", "AM").replace("م", "PM").replace(".", ":")
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM)?", text)
    if not m:
        raise ValueError(_text(value))
    hour, minute, half = int(m.group(1)), int(m.group(2)), m.group(3)
    if half == "PM" and hour < 12:
        hour += 12
    if half == "AM" and hour == 12:
        hour = 0
    if minute > 59 or hour > 24 or (hour == 24 and minute):
        raise ValueError(_text(value))
    return f"{hour:02d}:{minute:02d}"


def _minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _days(value) -> List[str]:
    parts = [p for p in re.split(r"[/,،\-\s]+|\s+و", _text(value)) if p]
    indexes = []
    for part in parts:
        index = _DAY_ALIASES.get(part.lower())
        if index is None and part.startswith("و"):
            index = _DAY_ALIASES.get(part[1:])
        if index is None:
            raise ValueError(part)
        if index not in indexes:
            indexes.append(index)
    if not indexes:
        raise ValueError("")
    return [DAYS[i] for i in sorted(indexes)]


def _exam(value) -> str:
    if isinstance(value, datetime):
        return value.strftime(EXAM_DATETIME_FORMAT)
    text = _text(value)
    if not text:
        return UNKNOWN
    if text in NO_EXAM_SENTINELS:
        return text
    # "15/12/2026 8:00 am" is accepted too; it is saved as "15-12-2026 08:00 AM".
    exam = parse_exam_datetime(text.replace("/", "-").upper())
    if exam is None:
        raise ValueError(text)
    return exam.strftime(EXAM_DATETIME_FORMAT)


def parse_excel(data: bytes) -> Tuple[List[dict], List[dict]]:
    """
    (offerings, problems). `problems` lists {"row", "column", "code", "value"}
    with the Excel row number and the column's header; offerings is only
    usable when problems is empty.
    """
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        raise OfferingsError("not_excel") from e
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        raise OfferingsError("no_header")

    aliases = {}
    for key, arabic, others in COLUMNS:
        for name in [arabic, *others]:
            aliases[_norm(name)] = key
    position: Dict[str, int] = {}
    for i, cell in enumerate(header):
        key = aliases.get(_norm(cell))
        if key and key not in position:
            position[key] = i
    missing = [arabic for key, arabic, _ in COLUMNS if key in REQUIRED_COLUMNS and key not in position]
    if missing:
        raise OfferingsError("missing_columns:" + "، ".join(missing))
    header_name = {key: arabic for key, arabic, _ in COLUMNS}

    problems: List[dict] = []
    courses: Dict[str, dict] = {}
    sections: Dict[Tuple[str, str], dict] = {}
    crns: Dict[str, Tuple[str, str]] = {}
    pending_prereqs: List[Tuple[int, str, str]] = []

    def problem(row, key, code, value=""):
        problems.append({"row": row, "column": header_name.get(key, key), "code": code, "value": _text(value)[:60]})

    for row_number, values in enumerate(rows, start=2):
        if row_number > MAX_ROWS + 1:
            problem(row_number, "code", "too_many_rows", MAX_ROWS)
            break
        cell = {key: (values[i] if i < len(values) else None) for key, i in position.items()}
        if all(_text(v) == "" for v in cell.values()):
            continue   # empty row

        code = _text(cell.get("code"))
        if not code:
            problem(row_number, "code", "missing")
            continue
        section_id = _text(cell.get("section"))
        if not section_id:
            problem(row_number, "section", "missing")

        # ---- course columns (filled on the course's first row; later rows may repeat them)
        course = courses.get(code)
        name = _text(cell.get("name"))
        credits_bad = False
        try:
            credits = _int(cell.get("credits"))
            if credits is not None and not 0 < credits <= 12:
                raise ValueError(credits)
        except ValueError:
            problem(row_number, "credits", "bad_number", cell.get("credits"))
            credits, credits_bad = None, True
        try:
            exam = _exam(cell.get("final_exam")) if _text(cell.get("final_exam")) or course is None else None
        except ValueError:
            problem(row_number, "final_exam", "bad_exam", cell.get("final_exam"))
            exam = None
        if course is None:
            if not name:
                problem(row_number, "name", "missing")
            if credits is None and not credits_bad:
                problem(row_number, "credits", "missing")
            course = {"code": code, "name": name, "credits": credits or 0, "prerequisites": [],
                      "final_exam": exam or UNKNOWN, "sections": [], "_row": row_number}
            courses[code] = course
            prereq_text = _text(cell.get("prerequisites"))
            for p in [p.strip() for p in re.split(r"[,،;\n]+", prereq_text) if p.strip()]:
                course["prerequisites"].append(p)
                pending_prereqs.append((row_number, code, p))
        else:
            if name and name != course["name"]:
                problem(row_number, "name", "course_mismatch", name)
            if credits is not None and credits != course["credits"]:
                problem(row_number, "credits", "course_mismatch", credits)
            if exam is not None and exam != course["final_exam"]:
                problem(row_number, "final_exam", "course_mismatch", cell.get("final_exam"))

        # ---- the meeting on this row
        meeting = None
        try:
            days = _days(cell.get("days"))
        except ValueError as e:
            problem(row_number, "days", "bad_days" if str(e) else "missing", cell.get("days"))
            days = None
        try:
            start = _time(cell.get("start"))
            if start is None:
                problem(row_number, "start", "missing")
        except ValueError:
            problem(row_number, "start", "bad_time", cell.get("start"))
            start = None
        try:
            end = _time(cell.get("end"))
            if end is None:
                problem(row_number, "end", "missing")
        except ValueError:
            problem(row_number, "end", "bad_time", cell.get("end"))
            end = None
        if start and end:
            if _minutes(end) <= _minutes(start):
                problem(row_number, "end", "end_before_start", f"{start} - {end}")
            elif _minutes(start) < EARLIEST or _minutes(end) > LATEST:
                problem(row_number, "start", "out_of_hours", f"{start} - {end}")
            elif days:
                meeting = {"days": days, "start": start, "end": end}

        # ---- section columns (on the section's first row)
        if not section_id:
            continue
        key = (code, section_id)
        section = sections.get(key)
        crn = _text(cell.get("crn"))
        instructor = _text(cell.get("instructor"))
        try:
            capacity = _int(cell.get("capacity"))
        except ValueError:
            problem(row_number, "capacity", "bad_number", cell.get("capacity"))
            capacity = None
        try:
            enrolled = _int(cell.get("enrolled"))
        except ValueError:
            problem(row_number, "enrolled", "bad_number", cell.get("enrolled"))
            enrolled = None

        if section is None:
            if not crn:
                problem(row_number, "crn", "missing")
            elif not re.fullmatch(r"\d{3,10}", crn):
                problem(row_number, "crn", "bad_crn", crn)
            elif crn in crns:
                problem(row_number, "crn", "duplicate_crn", crn)
            else:
                crns[crn] = key
            if capacity is not None and enrolled is not None and enrolled > capacity:
                problem(row_number, "enrolled", "over_capacity", f"{enrolled} / {capacity}")
            section = {"id": section_id, "crn": crn, "instructor": instructor,
                       "capacity": capacity, "enrolled": enrolled or 0, "meetings": []}
            sections[key] = section
            course["sections"].append(section)
        else:
            if crn and crn != section["crn"]:
                problem(row_number, "crn", "section_mismatch", crn)
            if instructor and instructor != section["instructor"]:
                problem(row_number, "instructor", "section_mismatch", instructor)
            if capacity is not None and capacity != section["capacity"]:
                problem(row_number, "capacity", "section_mismatch", capacity)
            if enrolled is not None and enrolled != section["enrolled"]:
                problem(row_number, "enrolled", "section_mismatch", enrolled)
        if meeting:
            if any(_overlaps(meeting, other) for other in section["meetings"]):
                problem(row_number, "start", "section_overlap", f"{meeting['start']} - {meeting['end']}")
            else:
                section["meetings"].append(meeting)

    for row_number, code, prereq in pending_prereqs:
        if prereq not in courses:
            problem(row_number, "prerequisites", "unknown_prereq", prereq)
        elif prereq == code:
            problem(row_number, "prerequisites", "self_prereq", prereq)

    if not courses and not problems:
        raise OfferingsError("empty")
    offerings = []
    for course in courses.values():
        course.pop("_row", None)
        offerings.append(course)
    problems.sort(key=lambda p: p["row"])
    return offerings, problems


def _overlaps(a: dict, b: dict) -> bool:
    return bool(set(a["days"]) & set(b["days"])) and \
        _minutes(a["start"]) < _minutes(b["end"]) and _minutes(b["start"]) < _minutes(a["end"])


# ---------------------------------------------------------------- storing

def load_saved() -> Optional[dict]:
    """{"courses": [...], "updated_at", "updated_by"} saved by the admin, or None."""
    from src.accounts import store

    raw = store.get_meta(META_KEY)
    if not raw:
        return None
    try:
        saved = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return saved if isinstance(saved, dict) and isinstance(saved.get("courses"), list) else None


def save(courses: List[dict], updated_by: str, file: Optional[bytes] = None,
         file_name: str = "") -> dict:
    """
    Saves the courses the site uses and, with them, the Excel file exactly as
    it was uploaded, so everyone who downloads it gets that same file.
    """
    from src.accounts import store
    from src.accounts.db import now_iso

    saved = {"courses": courses, "updated_at": now_iso(), "updated_by": updated_by}
    store.set_meta(META_KEY, json.dumps(saved, ensure_ascii=False))
    save_file(file if file is not None else to_excel(courses), file_name)
    return saved


def save_file(data: bytes, file_name: str = "") -> None:
    from src.accounts import store

    store.set_meta(FILE_KEY, json.dumps({
        "name": file_name or DEFAULT_FILE.name,
        "data": base64.b64encode(data).decode("ascii"),
    }))


def load_file() -> Optional[Tuple[bytes, str]]:
    """(the last uploaded Excel file, its name), or None if none was uploaded."""
    from src.accounts import store

    raw = store.get_meta(FILE_KEY)
    if not raw:
        return None
    try:
        saved = json.loads(raw)
        return base64.b64decode(saved["data"]), saved.get("name") or DEFAULT_FILE.name
    except (ValueError, KeyError, TypeError):
        return None


def default_file() -> bytes:
    """The Excel file kept in the project for the built-in data."""
    if DEFAULT_FILE.exists():
        return DEFAULT_FILE.read_bytes()
    return to_excel(default_offerings())


def clear_saved() -> None:
    from src.accounts import store

    store.set_meta(META_KEY, "")
    store.set_meta(FILE_KEY, "")
