"""
تحقّقات اختيار المقررات: المتطلبات السابقة، الحد الأقصى للساعات، ومجموعة الاختياريات.
منفصلة عن app.py لتكون قابلة للاختبار وإعادة الاستخدام (مثلاً لاحقاً داخل الـ CSP نفسه).
"""
from typing import Dict, List, Set

from .models import Course, Student


def check_prerequisites(target_courses: List[Course], completed_courses: List[str],
                         course_db: List[Course]) -> List[str]:
    """
    يرجع قائمة رسائل خطأ لكل مقرر هدف تنقصه متطلبات سابقة لم تُنجز بعد.
    قائمة فارغة تعني: لا يوجد تعارض في المتطلبات السابقة.
    """
    errors = []
    course_by_code = {c.code: c for c in course_db}

    for tc in target_courses:
        for prereq in tc.prerequisites:
            if prereq not in completed_courses:
                prereq_obj = course_by_code.get(prereq)
                prereq_name = prereq_obj.name if prereq_obj else prereq
                errors.append(
                    f"لا يمكنك تسجيل [ **{tc.name}** ] لأنك لم تجتز متطلبه السابق [ **{prereq_name}** ]"
                )
    return errors


def check_credit_hours(target_courses: List[Course], max_credit_hours: int) -> List[str]:
    """
    يرجع رسالة خطأ واحدة (كقائمة) إن تجاوز مجموع الساعات المختارة الحد الأقصى المسموح، وإلا قائمة فارغة.
    """
    total = sum(c.credit_hours for c in target_courses)
    if total > max_credit_hours:
        return [
            f"⚠️ إجمالي الساعات المختارة ({total} ساعة) يتجاوز الحد الأقصى المسموح ({max_credit_hours} ساعة). "
            f"الرجاء إزالة بعض المقررات."
        ]
    return []


def check_elective_pool_limit(target_courses: List[Course], elective_pool_codes: Set[str],
                               max_electives: int) -> List[str]:
    """
    يتحقق من عدم اختيار أكثر من max_electives من مجموعة مقررات اختيارية معينة
    (مثال: "علوم حاسب متطلبات اختيارية" التي يختار منها الطالب 3 فقط من أصل 19 حسب الخطة).
    """
    chosen = [c for c in target_courses if c.code in elective_pool_codes]
    if len(chosen) > max_electives:
        names = "، ".join(c.name for c in chosen)
        return [
            f"⚠️ اخترت {len(chosen)} مقررات من مجموعة الاختياريات ({names})، "
            f"والمسموح به حسب الخطة هو {max_electives} فقط. الرجاء إزالة البعض."
        ]
    return []


def validate_course_selection(target_courses: List[Course], student: Student,
                               course_db: List[Course], max_credit_hours: int,
                               elective_pool_codes: Set[str] = None,
                               max_electives: int = 3) -> List[str]:
    """
    يجمع كل رسائل الخطأ (متطلبات سابقة + حد الساعات + حد الاختياريات) في قائمة واحدة.
    قائمة فارغة = الاختيار صالح ويمكن المتابعة للجدولة.
    """
    errors = []
    errors.extend(check_prerequisites(target_courses, student.completed_courses, course_db))
    errors.extend(check_credit_hours(target_courses, max_credit_hours))
    if elective_pool_codes:
        errors.extend(check_elective_pool_limit(target_courses, elective_pool_codes, max_electives))
    return errors