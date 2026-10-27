"""
Answers that don't need retrieval or the LLM.

Modelled on how the college Telegram group's answer bot works:
- "ابي خطة علوم الحاسب" / "التقويم الدراسي" -> hand over the file itself.
- "متى يبدأ الحذف؟" / "متى الإجازة الجاية؟" -> just the date, with a
  countdown ("بعد 12 يوم"), read straight from the official calendar.

Both are exact lookups, so they are answered instantly and stay correct even
when the hosted LLM is rate-limited. Anything else returns None and goes
through the normal RAG path.
"""

import os
import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import quote

DOCS_DIR = os.environ.get("DATA_DIR", "docs")
CALENDAR_TXT = os.path.join(DOCS_DIR, "imamu_web", "academic_calendar", "التقويم_الدراسي_1448_1449.txt")
CALENDAR_PDF_URL = "https://units.imamu.edu.sa/deanships/admission/Documents/Calendar_1448.pdf"
CALENDAR_NAME = "التقويم الدراسي للعام الجامعي 1448/1449هـ"

STUDY_PLANS_DIR = "imamu_web/ccis/study_plans"
# Department regex -> (display name, plan file under DOCS_DIR)
PLANS = [
    # Not a bare "علوم": it is inside "المعلومات" too.
    (r"علوم\s*(ال)?حاسب|\bعلوم\b|\bcs\b|computer\s*science",
     "علوم الحاسب", f"{STUDY_PLANS_DIR}/الخطة_الدراسية_بكالوريوس_علوم_الحاسب_1447.pdf"),
    (r"تقني[هة]|\bit\b|information\s*technology",
     "تقنية المعلومات", f"{STUDY_PLANS_DIR}/الخطة_الدراسية_بكالوريوس_تقنية_المعلومات_1447.pdf"),
    (r"نظم|\bis\b|information\s*systems",
     "نظم المعلومات", f"{STUDY_PLANS_DIR}/الخطة_الدراسية_بكالوريوس_نظم_المعلومات_1447.pdf"),
]

# A question about something *inside* the plan/calendar, not a request for the file.
_DETAIL_RE = re.compile(
    r"متطلب|\b(كم|هل|وش|ايش|إيش|مين)\b|متى|كيف|ليش|ماد[هة]|مواد|مقرر|ساع[هة]|ساعات|شروط|الفرق|"
    r"مستوى|اختياري|حر[هة]|موعد|تاريخ|باقي|يبدأ|يبدا|ينتهي|ماجستير|دبلوم"
)
_PLAN_RE = re.compile(r"خط[هة]|خطط")
_CALENDAR_RE = re.compile(r"تقويم")
_DATE_Q_RE = re.compile(r"متى|تاريخ|موعد|كم\s*باقي|كم\s*يوم|ايش\s*يوم|أي\s*يوم|اي\s*يوم|وش\s*يوم")


def _file_link(label: str, rel_path: str) -> str:
    """A link the chat page turns into a download button: [label](url)."""
    return f"[📄 {label}](/data/{quote(rel_path)})"


def file_reply(message: str) -> str | None:
    """The study plan or calendar file, when the student asks for the whole thing."""
    text = message.lower()
    if _DETAIL_RE.search(text):
        return None

    if _PLAN_RE.search(text):
        wanted = [(name, path) for pattern, name, path in PLANS if re.search(pattern, text)]
        if wanted:
            lines = ["🌟 الخطة الدراسية بكالوريوس " + "، ".join(n for n, _ in wanted) + " (1447هـ)"]
            lines += [_file_link(f"خطة {name}", path) for name, path in wanted]
        else:
            lines = ["🌟 الخطط الدراسية لأقسام كلية علوم الحاسب والمعلومات (1447هـ)، اختر تخصصك:"]
            lines += [_file_link(f"خطة {name}", path) for _, name, path in PLANS]
        lines.append("إذا عندك سؤال عن مقرر معيّن أو متطلباته، اسألني عنه مباشرة.")
        return "\n".join(lines)

    if _CALENDAR_RE.search(text):
        return (
            f"🗓️ {CALENDAR_NAME} (الفصل الأول والثاني)\n"
            f"[📄 ملف التقويم الدراسي]({CALENDAR_PDF_URL})\n"
            "وإذا تبي موعد معيّن، اسألني مثلًا: متى يبدأ الحذف؟ أو متى الإجازة الجاية؟"
        )
    return None


# ---------------------------------------------------------------- calendar


@dataclass
class CalendarEvent:
    title: str
    semester: str          # "الفصل الدراسي الأول" / "الفصل الدراسي الثاني"
    start: date
    end: date
    start_text: str        # "الأحد 17/03/1448هـ الموافق 30/08/2026م"
    end_text: str | None   # same, for ranges with a separate end


_GREG_RE = re.compile(r"(\d{1,2})(?:-(\d{1,2}))?/(\d{1,2})/(\d{4})م")


def load_calendar(path: str = CALENDAR_TXT) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    semester = ""
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if line.startswith("--- Page"):
                semester = "الفصل الدراسي الأول" if "1" in line else "الفصل الدراسي الثاني"
                continue
            if not line.startswith("- ") or ":" not in line:
                continue
            title, rest = line[2:].split(":", 1)
            rest = rest.strip().rstrip(".")
            dates = _GREG_RE.findall(rest)
            if not dates:
                continue
            d1, d1b, m1, y1 = dates[0]
            start = date(int(y1), int(m1), int(d1))
            if len(dates) > 1:
                d2, _, m2, y2 = dates[1]
                end = date(int(y2), int(m2), int(d2))
            elif d1b:  # "23-24/09/2026م"
                end = date(int(y1), int(m1), int(d1b))
            else:
                end = start
            parts = re.split(r"،\s*و(?:ينتهي|تنتهي)\s*", rest)
            start_text = re.sub(r"^(يبدأ|تبدأ|تبدأ بنهاية دوام يوم)\s*", "", parts[0]).strip()
            end_text = parts[1].strip() if len(parts) > 1 else None
            events.append(CalendarEvent(title.strip(), semester, start, end, start_text, end_text))
    return events


# Student wording -> calendar entry titles it refers to (substring match).
TOPICS: list[tuple[str, list[str]]] = [
    # "الحذف والإضافة" together is the add/drop (registration) window, not withdrawal.
    (r"حذف\s*و\s*(ال)?[اإ]ضاف", ["تسجيل المقررات", "التسجيل الإلحاقي"]),
    (r"حذف|انسحاب|انسحب|اعتذار|اعتذر", ["الاعتذار عن الفصل الدراسي والانسحاب"]),
    (r"الحاقي|إلحاقي|اضاف[هة]|إضاف[هة]", ["التسجيل الإلحاقي"]),
    (r"تسجيل\s*(ال)?مقررات|تسجيل\s*(ال)?مواد|تنزيل\s*(ال)?مواد|انزل\s*(ال)?مواد|التسجيل", ["تسجيل المقررات"]),
    (r"تحويل\s*خارجي|التحويل\s*الخارجي|من\s*جامع[هة]\s*ثاني[هة]", ["التحويل الخارجي"]),
    (r"تحويل|احول|أحول", ["التحويل بين الكليات والأقسام"]),
    (r"تأجيل|تاجيل|اأجل|أأجل|اجل\s*الترم", ["التأجيل لبرامج الدبلوم والبكالوريوس"]),
    (r"اعاد[هة]\s*(ال)?قيد|إعاد[هة]\s*(ال)?قيد", ["إعادة القيد"]),
    (r"بديل|تكميلي", ["الاختبارات البديلة والتكميلية"]),
    (r"فاينل|النهائي|النهائيه|النهائية|الاختبارات", ["بداية الاختبارات النهائية"]),
    (r"اليوم\s*الوطني|الوطني", ["إجازة اليوم الوطني"]),
    (r"التأسيس|التاسيس", ["إجازة يوم التأسيس"]),
    (r"الخريف", ["بداية إجازة الخريف"]),
    (r"الفطر|عيد\s*رمضان", ["بداية إجازة عيد الفطر"]),
    (r"الأضحى|الاضحى|الحج", ["بداية إجازة عيد الأضحى"]),
    (r"منتصف\s*العام|نص\s*السن[هة]|بين\s*الترمين", ["إجازة منتصف العام الدراسي"]),
    (r"نهاي[هة]\s*العام|الصيف|اخر\s*السن[هة]|آخر\s*السن[هة]", ["بداية إجازة نهاية العام الدراسي للطلاب"]),
    (r"اجاز[هة]|إجاز[هة]|عطل[هة]", ["إجازة"]),
    (r"(يبدا|يبدأ|تبدأ|تبدا|بداي[هة]|يرجع|نرجع)\s*(ال)?(دوام|دراس[هة]|ترم)|الدوام|الدراسة", ["بداية الدراسة"]),
]


def _days_word(n: int) -> str:
    if n == 0:
        return "اليوم"
    if n == 1:
        return "بكرة"
    return f"{n} يوم"


def _pick(candidates: list[CalendarEvent], message: str, today: date) -> CalendarEvent | None:
    if re.search(r"الثاني|ثاني", message):
        candidates = [e for e in candidates if e.semester.endswith("الثاني")] or candidates
    elif re.search(r"الأول|الاول|اول", message):
        candidates = [e for e in candidates if e.semester.endswith("الأول")] or candidates
    if not re.search(r"عليا|ماجستير|دكتوراه", message):
        candidates = [e for e in candidates if "الدراسات العليا" not in e.title
                      and "تأجيل القبول" not in e.title] or candidates
    upcoming = sorted((e for e in candidates if e.end >= today), key=lambda e: e.start)
    return upcoming[0] if upcoming else None


def date_reply(message: str, today: date | None = None,
               events: list[CalendarEvent] | None = None) -> str | None:
    """Just the date of a calendar event the student asks about, else None."""
    if not _DATE_Q_RE.search(message):
        return None
    today = today or date.today()
    events = events if events is not None else load_calendar()

    for pattern, titles in TOPICS:
        if not re.search(pattern, message):
            continue
        candidates = [e for e in events if any(t in e.title for t in titles)]
        if titles == ["إجازة"]:  # "the next holiday": the next one that starts after today
            candidates = [e for e in candidates if e.start > today and "هيئة التدريس" not in e.title]
        event = _pick(candidates, message, today)
        if event is None:
            return None
        return _format(event, today)
    return None


def _format(e: CalendarEvent, today: date) -> str:
    head = e.title if "الفصل الدراسي" in e.title else f"{e.title} ({e.semester})"
    if e.end_text and e.start <= today <= e.end:
        body = f"🔸| متاح الآن: {head}\nوينتهي {e.end_text} [باقي {_days_word((e.end - today).days)}]"
    elif e.end_text:
        body = (f"🔹| {head}\nيبدأ {e.start_text} [بعد {_days_word((e.start - today).days)}]"
                f"\nوينتهي {e.end_text}")
    else:
        when = (e.start - today).days
        tail = f"[بعد {_days_word(when)}]" if when > 0 else "[اليوم]"
        body = f"🔹| {head}\n{e.start_text} {tail}"
    return f"{body}\n\nالمصدر: {CALENDAR_NAME}"


def quick_reply(message: str, today: date | None = None) -> str | None:
    """A file or a date, if the message is one of those requests; else None."""
    return date_reply(message, today) or file_reply(message)
