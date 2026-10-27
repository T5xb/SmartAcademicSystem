"""
قارئ السجل الأكاديمي (Transcript PDF Parser).

يعتمد على أن جداول السجل تتكرر بنفس الشكل عبر الصفحات:
- صف عنوان "Course Code | Course Title | (فارغ أحياناً) | C.Hours | Q Points | Grade" — يتكرر كترويسة
  متكررة أعلى كل صفحة، وليس مرة واحدة فقط لكل فصل، لذلك يُتجاهل أينما ظهر.
- صفوف مقررات: أول خانة = رمز المقرر، آخر 3 خانات = الساعات المعتمدة/نقاط الجودة/التقدير،
  وما بينهما (بعد إزالة القيم الفارغة None) = اسم المقرر.
- صف عنوان إحصائي "Hours | Registered | Passed | Earned | Q Points | GPA" — يُتجاهل أيضاً.
- صف "Term": إحصاء الفصل نفسه — غير مستخدم هنا.
- صف "Accumulative": الإحصاء التراكمي حتى تلك اللحظة؛ آخر صف من هذا النوع في المستند
  يمثل الوضع التراكمي الحالي (GPA والساعات المكتسبة).

هذا التصميم يتجاوز مشكلة انقسام جدول فصل واحد بين صفحتين (وهو ما يحدث فعلياً في نماذج
هذه الجامعة)، لأنه لا يعتمد على حدود الفصول إطلاقاً، بل يمر على كل الصفوف بالتسلسل.
"""
from dataclasses import dataclass, field
from typing import BinaryIO, List, Optional, Set, Union

import re

import pdfplumber

# تقدير اصطلاحي لمقرر معادَل (منقول من جهة أخرى) — يظهر في السجل بلا تقدير ولا نقاط
EQUIVALENT_GRADE = "EQ"

# تقديرات لا تُحتسب كنجاح في المقرر (رسوب / انسحاب / لم يحضر / قيد التنفيذ)
NON_PASSING_GRADES = {"F", "W", "DN", "IP", "IC"}

# صفوف تُستبعد من كونها "مقرراً" لأنها ترويسات متكررة أو إحصاءات فصلية
_HEADER_FIRST_CELLS = {"Course Code", "Hours", "Term", "Accumulative"}


@dataclass
class TranscriptCourseRecord:
    code: str
    title: str
    credit_hours: float
    grade: str

    @property
    def passed(self) -> bool:
        return self.grade.strip().upper() not in NON_PASSING_GRADES and self.credit_hours > 0


@dataclass
class TranscriptData:
    student_name: Optional[str] = None
    student_id: Optional[str] = None
    college: Optional[str] = None
    major: Optional[str] = None

    courses: List[TranscriptCourseRecord] = field(default_factory=list)

    cumulative_gpa: Optional[float] = None
    cumulative_registered_hours: Optional[int] = None
    cumulative_passed_hours: Optional[int] = None
    cumulative_earned_hours: Optional[int] = None

    parse_warnings: List[str] = field(default_factory=list)

    def completed_course_codes(self) -> Set[str]:
        """رموز المقررات التي اجتازها الطالب في محاولة واحدة على الأقل (حتى لو رسب فيها سابقاً)."""
        return {c.code for c in self.courses if c.passed}

    def failed_or_withdrawn_course_codes(self) -> Set[str]:
        """رموز حاول فيها الطالب ولم ينجح في أي محاولة (لعرضها كتنبيه، مثل مقرر لا يزال يرسب فيه)."""
        completed = self.completed_course_codes()
        return {c.code for c in self.courses if not c.passed} - completed


def _to_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: str) -> Optional[int]:
    f = _to_float(value)
    return int(f) if f is not None else None


_COURSE_CODE_RE = re.compile(r"^[A-Z]{2,5} ?\d{3,4}$")


def _looks_like_course_code(value: str) -> bool:
    return bool(_COURSE_CODE_RE.match(str(value).strip()))


def _parse_course_row(row: List[Optional[str]]) -> Optional[TranscriptCourseRecord]:
    """
    يحلل صف مقرر واحد بغض النظر عن وجود خانة None إضافية بين الرمز والعنوان
    (بعض صفحات المستند تُصدّر عمود عنوان إضافي فارغ، وبعضها لا).
    """
    cells = [c for c in row if c is not None and str(c).strip() != ""]
    if len(cells) == 3 and _looks_like_course_code(cells[0]):
        # جدول "المقررات المعادلة" أعلى السجل: رمز | اسم | ساعات، بلا تقدير.
        # هذه مقررات محتسبة للطالب (ضمن الساعات المكتسبة)، فتُعامل كمجتازة.
        hours = _to_float(cells[2])
        if hours is None:
            return None
        return TranscriptCourseRecord(code=cells[0].strip(), title=cells[1].strip(),
                                      credit_hours=hours, grade=EQUIVALENT_GRADE)
    if len(cells) < 4:
        return None  # صف غير مكتمل، لا يمكن اعتباره مقرراً بثقة

    code = cells[0].strip()
    grade = cells[-1].strip()
    q_points = cells[-2].strip()
    credit_hours_str = cells[-3].strip()
    title = " ".join(cells[1:-3]).strip()

    credit_hours = _to_float(credit_hours_str)
    if credit_hours is None:
        return None  # لا نخمّن رقماً؛ نتجاهل الصف بدل افتراض قيمة قد تكون خاطئة

    return TranscriptCourseRecord(code=code, title=title, credit_hours=credit_hours, grade=grade)


def parse_transcript(pdf_source: Union[str, BinaryIO]) -> TranscriptData:
    """
    يحلل ملف PDF لسجل أكاديمي (نصي وليس ممسوحاً ضوئياً) ويرجع TranscriptData.
    pdf_source: مسار ملف، أو كائن ملف (مثل ما يرجعه st.file_uploader في Streamlit).
    """
    data = TranscriptData()

    with pdfplumber.open(pdf_source) as pdf:
        # معلومات الطالب من نص الصفحة الأولى (وليست جدولاً، لذا تُستخرج بالنص)
        first_page_text = pdf.pages[0].extract_text() or ""

        def _strip_label(text: str, label: str) -> str:
            """
            يزيل التسمية (مثل "Name") من بداية السطر، ثم أي فاصل شائع بعدها (نقطتان أو
            شرطة) مع المسافات المحيطة به. يتحمل كلا الشكلين: "Name John" و"Name: John".
            """
            value = text.replace(label, "", 1).strip()
            return value.lstrip(":-").strip()

        for line in first_page_text.splitlines():
            line = line.strip()
            if line.startswith("Name") and data.student_name is None:
                data.student_name = _strip_label(line, "Name")
            elif line.startswith("Student Id") and data.student_id is None:
                # الشكل المعتاد: "Student Id 123456789 Born In 2000" أو "Student Id: 123456789 ..."
                parts = _strip_label(line, "Student Id").split()
                if parts:
                    data.student_id = parts[0]
            elif line.startswith("College") and data.college is None:
                data.college = _strip_label(line, "College")
            elif line.startswith("Major") and data.major is None:
                major_val = _strip_label(line, "Major")
                if major_val:
                    data.major = major_val

        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if not row or row[0] is None:
                        continue
                    first_cell = str(row[0]).strip()

                    if (first_cell in ("Course Code", "Hours", "Term")
                            or first_cell.startswith("Equivalent Credit Hours")):
                        continue  # ترويسات متكررة أو إحصاء فصل غير مستخدم هنا

                    if first_cell == "Accumulative":
                        # آخر صف "تراكمي" في المستند بأكمله = الوضع الحالي؛ نستمر بالكتابة فوق القيم
                        cells = [c for c in row if c is not None]
                        if len(cells) >= 6:
                            data.cumulative_registered_hours = _to_int(cells[1])
                            data.cumulative_passed_hours = _to_int(cells[2])
                            data.cumulative_earned_hours = _to_int(cells[3])
                            data.cumulative_gpa = _to_float(cells[5])
                        continue

                    record = _parse_course_row(row)
                    if record is not None:
                        data.courses.append(record)
                    else:
                        data.parse_warnings.append(f"تعذّر تحليل صف: {row}")

    if not data.courses:
        data.parse_warnings.append("لم يتم العثور على أي مقررات في الملف — تأكد أن السجل نصي (غير ممسوح ضوئياً كصورة).")

    return data