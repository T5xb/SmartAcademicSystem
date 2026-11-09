"""
Email lookups: "وش ايميل لجنة مشاريع التخرج نظم؟" / "ايميل د. لميس الهزاع".

Read from the college contact directory (docs/imamu_web/ccis/دليل_التواصل.md),
one "- label | dept or role | email | phone" line per unit or faculty member.
A question names a department, a unit/committee, a person, or a mix; the
reply lists the matching emails. When a department has no published email for
the asked unit (e.g. the CS graduation projects committee), the reply says so
and gives that department's office and advising emails instead of another
department's.
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache

DOCS_DIR = os.environ.get("DATA_DIR", "docs")
CONTACTS_MD = os.path.join(DOCS_DIR, "imamu_web", "ccis", "دليل_التواصل.md")
SOURCE_NAME = "دليل التواصل - كلية علوم الحاسب والمعلومات (موقع الجامعة)"

_ASK_RE = re.compile(r"[اإأ]يمي?ل|[اإأ]يميلات|بريد|e-?mail|\bmail\b|\bميل\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

CS, IS, IT, COLLEGE = "علوم الحاسب", "نظم المعلومات", "تقنية المعلومات", "الكلية"
UNIVERSITY = "الجامعة"  # university deanships: the same for every department
_URL_RE = re.compile(r"https?://\S+")
# Department wording. Not a bare "علوم": it is inside "المعلومات" too.
DEPTS = [
    (re.compile(r"علوم\s*(ال)?حاسب|\bعلوم\b|\bcs\b|computer\s*science|حاسب", re.I), CS),
    (re.compile(r"نظم|\bis\b|information\s*systems", re.I), IS),
    (re.compile(r"تقني[هة]|\bit\b|information\s*technology", re.I), IT),
]
_COLLEGE_RE = re.compile(r"عميد|عماد[هة]|وكيل|وكال[هة]|الكلي[هة]")
# University deanships (admission, student affairs...), not the college's own.
_OTHER_DEANSHIP_RE = re.compile(r"عماد[هة]\s*(ال)?(قبول|تسجيل|شؤون|شئون|دراسات|تقني|تعلم|بحث|خدم|مكتب|جود|تطوير)\w*")

# Student wording -> words of the unit labels it refers to (normalized, see _norm).
TOPICS: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"مشاريع|مشروع|تخرج|\bgp\b|جرادج", re.I), ["مشاريع تخرج"]),
    (re.compile(r"نفسي|اجتماعي"), ["ارشاد اجتماعي"]),
    (re.compile(r"[اإ]رشاد|مرشد|ادفايزر|advis", re.I), ["ارشاد اكاديمي"]),
    (re.compile(r"سكرتير|سكرتاري|سكرتار"), ["سكرتير", "سكرتاريه"]),
    (re.compile(r"امين|أمين"), ["امين"]),
    (re.compile(r"رئيس[هة]?\s*(ال)?قسم"), ["رئيس قسم"]),
    (re.compile(r"عميد|عماد[هة](?!\s*(ال)?(قبول|تسجيل|شؤون|شئون|دراسات|تقني|تعلم|بحث|خدم|مكتب|جود|تطوير))"),
     ["عماده كليه"]),
    (re.compile(r"قبول|تسجيل"), ["قبول تسجيل"]),
    (re.compile(r"شؤون\s*(ال)?طلاب|شئون\s*(ال)?طلاب"), ["شؤون طلاب"]),
    (re.compile(r"تعلم\s*(ال)?[اإ]لكتروني|بلا?ك\s*بورد|blackboard|عماد[هة]\s*(ال)?تقني|دعم\s*(ال)?فني", re.I),
     ["تعلم الكتروني"]),
    (re.compile(r"وكيل|وكال[هة]"), ["وكاله كليه"]),
    (re.compile(r"تدريب|تعاوني|كوب|co-?op", re.I), ["تدريب"]),
    (re.compile(r"اختبار|امتحان"), ["اختبارات"]),
    (re.compile(r"ماجستير|عليا|ماستر|master", re.I), ["ماجستير", "دراسات عليا"]),
    (re.compile(r"ذكاء\s*(ال)?[اإ]صطناعي|\bai\b", re.I), ["ذكاء اصطناعي"]),
    (re.compile(r"[اأ]من\s*(ال)?معلومات|سيبراني", re.I), ["امن معلومات"]),
    (re.compile(r"بكالوريوس"), ["بكالوريوس"]),
    (re.compile(r"خريج"), ["خريجين"]),
    (re.compile(r"مجتمعي|تطوع"), ["خدمات مجتمعيه"]),
    (re.compile(r"جود[هة]"), ["جوده"]),
    (re.compile(r"منا[هة]ج|خطط"), ["خطط مناهج"]),
    (re.compile(r"بحث\s*(ال)?علمي|ابحاث"), ["بحث علمي"]),
    (re.compile(r"مجلس\s*(ال)?استشاري|مجلس\s*(ال)?طلاب"), ["مجلس استشاري"]),
]
_PERSON_RE = re.compile(r"\bد\s*\.|دكتور|دكتوره|دكتورة|\bدكت|بروف|استاذ|أستاذ|\bأ\s*\.\s*د")

# Name words too common to identify one person on their own.
_COMMON_NAME_WORDS = {
    "محمد", "احمد", "عبدالله", "عبد", "الله", "بن", "بنت", "عبدالعزيز", "عبدالرحمن",
    "ابراهيم", "علي", "سعد", "خالد", "فهد", "سعود", "صالح", "ناصر", "سليمان", "حمد",
}
_TITLE_WORDS = {"د", "ا", "دكتور", "دكتوره", "استاذ", "بروف", "بروفيسور", "م"}


@dataclass
class Contact:
    label: str      # "لجنة مشاريع التخرج (طلاب)" / "د. لميس ... الهزاع"
    dept: str       # department, or the person's role for faculty
    email: str
    phone: str
    person: bool    # a faculty member (from the faculty section)


def _norm(text: str) -> str:
    """Spelling-insensitive form: no "ال", no hamza/taa-marbuta variants."""
    text = re.sub("[أإآ]", "ا", text).replace("ة", "ه").replace("ى", "ي").lower()
    return " ".join(re.sub(r"^(ال|وال|لل)(?=..)", "", w) for w in re.findall(r"\w+", text))


@lru_cache(maxsize=1)
def load_contacts(path: str = CONTACTS_MD) -> tuple[Contact, ...]:
    contacts: list[Contact] = []
    person = False
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if line.startswith("## "):
                person = "هيئة التدريس" in line
                continue
            if not line.startswith("- ") or "|" not in line:
                continue
            parts = [p.strip() for p in line[2:].split("|")]
            # A unit with no published email has its official contact link instead.
            email = next((p for p in parts if _EMAIL_RE.fullmatch(p) or _URL_RE.fullmatch(p)), None)
            if not email:
                continue
            label, dept = parts[0], parts[1] if len(parts) > 1 else ""
            phone = parts[3] if len(parts) > 3 else ""
            contacts.append(Contact(label, dept, email, phone, person))
    return tuple(contacts)


def _asked_depts(message: str) -> list[str]:
    # "كلية علوم الحاسب والمعلومات" is the college, not the CS department.
    message = re.sub(r"كلي[هة]\s*علوم\s*(ال)?حاسب(\s*و\s*(ال)?معلومات)?", "الكلية", message)
    # "عمادة تقنية المعلومات" is a university deanship, not the IT department or the college.
    message = _OTHER_DEANSHIP_RE.sub(" ", message)
    depts = [name for pattern, name in DEPTS if pattern.search(message)]
    if _COLLEGE_RE.search(message):
        depts.append(COLLEGE)
    return depts


def _has_words(label: str, words: str) -> bool:
    return all(w in _norm(label).split() for w in words.split())


def _topic_matches(message: str, units: list[Contact]) -> tuple[list[str], list[Contact]]:
    """The asked topics and the units whose labels match every one of them."""
    topics = [words for pattern, words in TOPICS if pattern.search(message)]
    if not topics:
        return [], []
    if ["ارشاد اجتماعي"] in topics:  # "الإرشاد النفسي" is not academic advising
        topics = [t for t in topics if t != ["ارشاد اكاديمي"]]
    found = [u for u in units if all(any(_has_words(u.label, w) for w in ws) for ws in topics)]
    return topics, found


def _name_matches(message: str, people: list[Contact]) -> list[Contact]:
    """Faculty whose name the message names: a distinctive word, or two words."""
    asked = set(_norm(message).split()) - _TITLE_WORDS
    best, found = 0, []
    for p in people:
        words = set(_norm(p.label).split()) - _TITLE_WORDS
        hits = asked & words
        rare = hits - _COMMON_NAME_WORDS
        score = len(hits) + len(rare)  # a rare word counts double
        if not rare and len(hits) < 2:
            continue
        if score > best:
            best, found = score, [p]
        elif score == best:
            found.append(p)
    return found if len(found) <= 6 else []


def _line(c: Contact) -> str:
    phone = "" if not c.phone else f" ☎️ {c.phone}" if c.phone[0].isdigit() else f"\n{c.phone}"
    if c.person:
        role = f" ({c.dept})" if c.dept else ""
        return f"🔹| {c.label}{role}\n📧 {c.email}"
    dept = f" - قسم {c.dept}" if c.dept in (CS, IS, IT) and c.dept not in c.label else ""
    icon = "🔗 نظام تواصل:" if _URL_RE.fullmatch(c.email) else "📧"
    return f"🔹| {c.label}{dept}\n{icon} {c.email}{phone}"


def _dept_main(units: list[Contact], dept: str) -> list[Contact]:
    """A department's general contacts: head, secretary/office, advising."""
    return [u for u in units if u.dept == dept and re.search(r"رئيس قسم|سكرتير|سكرتارية|الإرشاد الأكاديمي", u.label)
            and "عليا" not in u.label]


def email_reply(message: str, contacts: tuple[Contact, ...] | None = None) -> str | None:
    """The email(s) the student asks for, else None."""
    if not _ASK_RE.search(message):
        return None
    if contacts is None:
        try:
            contacts = load_contacts()
        except OSError:
            return None
    units = [c for c in contacts if not c.person]
    people = [c for c in contacts if c.person]
    depts = _asked_depts(message)
    footer = f"\n\nالمصدر: {SOURCE_NAME}"

    topics, found = _topic_matches(message, units)
    if topics:
        in_dept = [u for u in found if u.dept in depts or u.dept == UNIVERSITY] if depts else found
        if in_dept:
            reply = "\n\n".join(_line(u) for u in in_dept)
            # A department-level unit asked without a department, e.g. "لجنة المشاريع":
            # say which departments have no published email for it.
            have = {u.dept for u in in_dept}
            program = any(t[0] in ("ماجستير", "ذكاء اصطناعي", "امن معلومات", "بكالوريوس") for t in topics)
            if not depts and not program and have <= {CS, IS, IT}:
                missing = [d for d in (CS, IS, IT) if d not in have]
                if missing:
                    reply += "\n\n(ما لقيت إيميل منشور لهذي الجهة في قسم " + " وقسم ".join(missing) + ")"
            return reply + footer
        if depts and found:
            # The unit exists in another department but not in the asked one:
            # say so, and give the asked department's own contacts instead.
            dept = next(d for d in depts if d != COLLEGE) if any(d != COLLEGE for d in depts) else depts[0]
            fallback = _dept_main(units, dept)
            msg = (f"ما لقيت إيميل منشور لهذي الجهة في قسم {dept} بالمصادر الرسمية."
                   + (f"\nتقدر تتواصل مع القسم على:\n\n" + "\n\n".join(_line(u) for u in fallback) if fallback else ""))
            return msg + footer

    if _PERSON_RE.search(message) or not topics:
        named = _name_matches(message, people)
        if named:
            return "\n\n".join(_line(p) for p in named) + footer

    if not topics and depts:
        main = [u for u in units if u.dept == COLLEGE] if depts == [COLLEGE] else \
            [u for d in depts if d != COLLEGE for u in _dept_main(units, d)]
        if main:
            return "\n\n".join(_line(u) for u in main) + footer
    return None
