"""
Data models for the Smart Academic Advising System.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

# قيم اصطلاحية تعني "لا يوجد اختبار نهائي / غير محدد بعد" — لا تُعتبر تعارضاً أبداً
NO_EXAM_SENTINELS = {"غير محدد", "بدون اختبار"}
EXAM_DATETIME_FORMAT = "%d-%m-%Y %I:%M %p"  # مثال: "15-12-2026 08:00 AM"


def parse_exam_datetime(exam_str: str) -> Optional[datetime]:
    """
    يحوّل نص موعد الاختبار النهائي إلى datetime قابل للمقارنة الرقمية،
    بدلاً من الاعتماد على تطابق النص حرفياً (والذي ينكسر بصمت مع أي
    فرق بسيط في التنسيق مثل مسافة زائدة أو حالة أحرف مختلفة).
    يرجع None لكل من: بدون اختبار، غير محدد، أو أي نص لا يمكن تحليله.
    """
    if not exam_str or exam_str.strip() in NO_EXAM_SENTINELS:
        return None
    try:
        return datetime.strptime(exam_str.strip(), EXAM_DATETIME_FORMAT)
    except ValueError:
        # تنسيق غير متوقع: لا نفترض تعارضاً أو عدمه، فقط نُبلغ بعدم القدرة على التحليل
        return None


@dataclass
class TimeSlot:
    """Represents a single time slot in the timetable."""
    index: int
    start_time: str            # "HH:MM", 24h zero-padded
    end_time: str               # "HH:MM", 24h zero-padded
    label: str                  # display string, e.g. "الأحد/الثلاثاء 08:00-09:15"
    days: List[str] = field(default_factory=list)  # e.g. ["الأحد", "الثلاثاء"] — explicit, not parsed from label

    def __hash__(self):
        return hash(self.index)

    def start_minutes(self) -> int:
        """start_time converted to minutes since midnight, for numeric comparison."""
        h, m = map(int, self.start_time.split(":"))
        return h * 60 + m

    def end_minutes(self) -> int:
        h, m = map(int, self.end_time.split(":"))
        return h * 60 + m

@dataclass
class CourseSection:
    """تمثل شعبة معينة لمقرر دراسي"""
    section_id: str            # رقم الشعبة (مثال: 371)
    course_code: str           # رمز المقرر (مثال: CS311)
    time_slots: List[TimeSlot] # الأوقات والأيام التي تدرس فيها هذه الشعبة
    doctor_name: str = "غير محدد"
    capacity: Optional[int] = None   # الطاقة الاستيعابية؛ None تعني "غير محدودة" (H5)
    enrolled: int = 0                # عدد المسجَّلين حالياً؛ بيانات توضيحية لحين ربطها بنظام تسجيل فعلي

    def has_open_seats(self) -> bool:
        """H5: شعبة بلا سعة محددة تُعتبر دائماً متاحة؛ غير ذلك تُقارن السعة بعدد المسجَّلين."""
        return self.capacity is None or self.enrolled < self.capacity

@dataclass
class Course:
    """يمثل المقرر الدراسي"""
    code: str
    name: str
    credit_hours: int
    prerequisites: List[str]
    available_sections: List['CourseSection']
    final_exam: str = "غير محدد" # <--- الإضافة الجديدة (وقت الاختبار النهائي)
@dataclass
class Student:
    """يمثل الطالب وحالته الأكاديمية"""
    student_id: str
    completed_courses: List[str] # قائمة برموز المقررات التي اجتازها الطالب (تأتي من الـ Transcript)
    target_courses: List[Course] # المقررات التي يرغب الطالب أو النظام بتسجيلها له