"""
Constraint Satisfaction Problem (CSP) based timetable scheduler.

هذا الإصدار يضيف: تصفية النطاق مرة واحدة قبل البحث (node consistency، بما فيها H5
سعة المقاعد)، ترتيب المقررات ديناميكياً بأقل نطاق متبقٍ (MRV)، تجربة الشعب بترتيب
الأقل تقييداً على المقررات الأخرى (LCV)، تقليم النطاقات بعد كل إسناد (forward
checking)، وتشخيص مبسّط لسبب فشل الجدولة عند عدم وجود حل.
"""
from typing import Dict, List, Optional
from .models import Student, Course, CourseSection, parse_exam_datetime


class StudentCSPScheduler:
    def __init__(self, student: Student, pinned_sections: Dict[str, str] = None,
                 off_days: List[str] = None, start_time: str = "00:00", end_time: str = "23:59",
                 preferred_instructors: Dict[str, str] = None, min_days_off: int = 0):
        self.student = student
        self.target_courses = student.target_courses
        self.pinned_sections = pinned_sections or {}
        self.off_days = off_days or []
        self.start_time = start_time
        self.end_time = end_time
        # S3: تفضيل الدكتور — dict اختياري {رمز المقرر: اسم الدكتور المفضّل}
        self.preferred_instructors = preferred_instructors or {}
        # عدد أيام الأوف المطلوبة كحد أدنى (أي يوم من الأيام الخمسة)، بدل تحديد أيام بعينها
        self.max_days = 5 - max(0, min(5, min_days_off))

        self.all_schedules: List[Dict[str, CourseSection]] = []
        # سبب الفشل إن لم يوجد أي حل — يُملأ بعد solve_all() فقط عند الفشل
        self.failure_reason: Optional[str] = None
        self._deepest_count = -1
        self._deepest_course_code = None
        self._limit = 5

        # node consistency: تُبنى نطاقات كل مقرر مرة واحدة قبل البحث، بعد استبعاد
        # الشعب التي تخالف H5 (السعة)، H6 (التثبيت) أو H7 (نافذة الوقت/أيام الأوف)
        self.domains: Dict[str, List[CourseSection]] = {
            course.code: self._initial_domain(course) for course in self.target_courses
        }

    # ---------- بناء النطاقات والتحقق من القيود الأحادية ----------

    def _initial_domain(self, course: Course) -> List[CourseSection]:
        sections = course.available_sections
        if course.code in self.pinned_sections:  # H6
            pinned_id = self.pinned_sections[course.code]
            sections = [s for s in sections if s.section_id == pinned_id]
        sections = [s for s in sections if s.has_open_seats()]  # H5
        sections = [s for s in sections if self._within_time_window(s)]  # H7
        return sections

    def _within_time_window(self, section: CourseSection) -> bool:
        start_bound = self._to_minutes(self.start_time)
        end_bound = self._to_minutes(self.end_time)
        for ts in section.time_slots:
            if any(off_day in ts.days for off_day in self.off_days):
                return False
            if ts.start_minutes() < start_bound or ts.end_minutes() > end_bound:
                return False
        return True

    @staticmethod
    def _to_minutes(t: str) -> int:
        h, m = map(int, t.split(":"))
        return h * 60 + m

    # ---------- التحقق من H2 (تعارض المحاضرات) و H3 (تعارض الفاينل) ----------

    def _is_conflict(self, section1: CourseSection, section2: CourseSection) -> bool:
        slots1 = {ts.index for ts in section1.time_slots}
        slots2 = {ts.index for ts in section2.time_slots}
        return len(slots1.intersection(slots2)) > 0

    def _exam_clash(self, course1: Course, course2: Course) -> bool:
        exam1 = parse_exam_datetime(course1.final_exam)
        exam2 = parse_exam_datetime(course2.final_exam)
        return exam1 is not None and exam2 is not None and exam1 == exam2

    def _consistent(self, section: CourseSection, current_course: Course,
                     assignments: Dict[str, CourseSection]) -> bool:
        if self.max_days < 5:
            days = {d for ts in section.time_slots for d in ts.days}
            for assigned in assignments.values():
                days.update(d for ts in assigned.time_slots for d in ts.days)
            if len(days) > self.max_days:
                return False
        for assigned_code, assigned_section in assignments.items():
            assigned_course = next((c for c in self.target_courses if c.code == assigned_code), None)
            if assigned_course is None:
                continue  # لا يفترض حدوثه؛ نتجاوزه بدل انهيار البرنامج بالكامل
            if self._exam_clash(current_course, assigned_course):
                return False
            if self._is_conflict(section, assigned_section):
                return False
        return True

    # ---------- MRV و LCV ----------

    def _course_by_code(self, code: str) -> Course:
        return next(c for c in self.target_courses if c.code == code)

    def _select_unassigned(self, assignments: Dict[str, CourseSection],
                            domains: Dict[str, List[CourseSection]]) -> Optional[Course]:
        """MRV: يختار المقرر غير المُسنَد صاحب أقل عدد شعب متبقية في نطاقه الحالي."""
        unassigned = [c for c in self.target_courses if c.code not in assignments]
        if not unassigned:
            return None
        return min(unassigned, key=lambda c: len(domains[c.code]))

    def _order_by_lcv(self, course: Course, domains: Dict[str, List[CourseSection]],
                       assignments: Dict[str, CourseSection]) -> List[CourseSection]:
        """LCV: يجرّب أولاً الشعبة التي تُلغي أقل عدد من خيارات المقررات الأخرى غير المُسنَدة."""
        other_codes = [c.code for c in self.target_courses
                        if c.code != course.code and c.code not in assignments]

        def removals(section: CourseSection) -> int:
            count = 0
            for other_code in other_codes:
                for other_section in domains[other_code]:
                    if self._is_conflict(section, other_section):
                        count += 1
            return count

        return sorted(domains[course.code], key=removals)

    def _forward_check(self, assigned_course: Course, section: CourseSection,
                        domains: Dict[str, List[CourseSection]],
                        assignments: Dict[str, CourseSection]) -> Dict[str, List[CourseSection]]:
        """يُنتج نسخة من domains بعد إزالة كل شعبة من نطاقات المقررات الأخرى غير
        المُسنَدة بعد تتعارض (وقتاً أو فاينل) مع الشعبة المُسنَدة توّاً."""
        new_domains = {code: list(secs) for code, secs in domains.items()}
        for code, sections in new_domains.items():
            if code == assigned_course.code or code in assignments:
                continue
            other_course = self._course_by_code(code)
            new_domains[code] = [
                s for s in sections
                if not self._is_conflict(s, section)
                and not self._exam_clash(other_course, assigned_course)
            ]
        return new_domains

    # ---------- البحث الرئيسي ----------

    def solve_all(self, limit: int = 5) -> bool:
        self._limit = limit
        self.all_schedules = []
        self.failure_reason = None
        self._deepest_count = -1
        self._deepest_course_code = None
        initial_domains = {code: list(secs) for code, secs in self.domains.items()}
        self._backtrack({}, initial_domains)
        if not self.all_schedules:
            self._set_failure_reason()
        return len(self.all_schedules) > 0

    def _backtrack(self, assignments: Dict[str, CourseSection],
                   domains: Dict[str, List[CourseSection]]) -> bool:
        if len(assignments) == len(self.target_courses):
            self.all_schedules.append(assignments.copy())
            return len(self.all_schedules) >= self._limit

        course = self._select_unassigned(assignments, domains)
        depth = len(assignments)
        if depth > self._deepest_count:
            self._deepest_count = depth
            self._deepest_course_code = course.code

        for section in self._order_by_lcv(course, domains, assignments):
            if not self._consistent(section, course, assignments):
                continue
            new_domains = self._forward_check(course, section, domains, assignments)
            # لو إسناد هذه الشعبة يُفرغ نطاق مقرر آخر لم يُسنَد بعد، نتجاوزها فوراً
            # بدل النزول أعمق لنكتشف الفشل متأخراً (هذا هو forward checking)
            if any(len(new_domains[c.code]) == 0 for c in self.target_courses
                   if c.code not in assignments and c.code != course.code):
                continue

            assignments[course.code] = section
            if self._backtrack(assignments, new_domains):
                return True
            del assignments[course.code]

        return False

    def _set_failure_reason(self):
        empty_from_start = [c for c in self.target_courses if not self.domains[c.code]]
        if empty_from_start:
            names = "، ".join(c.name for c in empty_from_start)
            self.failure_reason = (
                f"لا توجد أي شعبة متاحة ضمن القيود المحددة (الأيام/الوقت/السعة/الشعبة "
                f"المثبتة) للمقرر التالي: {names}."
            )
        elif self._deepest_course_code:
            course = self._course_by_code(self._deepest_course_code)
            self.failure_reason = (
                f"تعذّر إيجاد جدول خالٍ من التعارض. أعمق نقطة وصل إليها البحث كانت عند "
                f"إسناد مقرر «{course.name}» — هو على الأرجح (أو أحد المقررات المُسنَدة "
                f"قبله) سبب التعارض. جرّب إزالته أو تخفيف قيود الوقت/الأيام."
            )
        else:
            self.failure_reason = "تعذّر إيجاد جدول خالٍ من التعارض."

    def get_all_schedules(self) -> List[Dict[str, CourseSection]]:
        return self.all_schedules


def evaluate_schedule(schedule: Dict[str, CourseSection], prefer_morning: bool = False,
                       preferred_instructors: Dict[str, str] = None,
                       weights: Dict[str, float] = None) -> float:
    """
    تقييم الجدول لترتيب الجداول المتعددة من الأفضل للأسوأ. مجموع موزون (0-100) لأربعة
    مقاييس مُطبَّعة بين 0 و1، كل مقياس يُهمَل (يُعامَل كمحايد = 1) إن لم يطلبه الطالب:

      f_days     : (S1) نسبة الأيام الحرة من أصل 5.
      f_gap      : (S2) معكوس متوسط الفجوة الخاملة بين المحاضرات في كل يوم نشِط.
      f_morning  : تفضيل الدوام الصباحي (فعّال فقط إذا prefer_morning=True).
      f_instr    : (S3) نسبة المقررات التي دكتورها المُسنَد يطابق التفضيل المُعطى.
    """
    weights = weights or {"days": 0.3, "gap": 0.3, "morning": 0.2, "instructor": 0.2}
    preferred_instructors = preferred_instructors or {}

    used_days = set()
    day_meetings: Dict[str, List[int]] = {}
    start_times_minutes = []

    for section in schedule.values():
        for ts in section.time_slots:
            used_days.update(ts.days)
            start_times_minutes.append(ts.start_minutes())
            for day in ts.days:
                day_meetings.setdefault(day, []).extend([ts.start_minutes(), ts.end_minutes()])

    # f_days: أيام حرة / 5
    f_days = max(0.0, (5 - len(used_days))) / 5

    # f_gap: لكل يوم فيه أكثر من محاضرة، نحسب الفجوات بين نهاية محاضرة وبداية التالية
    gaps = []
    for day, times in day_meetings.items():
        # كل عنصرين متتاليين (start, end) لنفس المحاضرة؛ نعيد تجميعها إلى فترات ثم نرتبها
        intervals = sorted(zip(times[0::2], times[1::2]))
        for (s1, e1), (s2, e2) in zip(intervals, intervals[1:]):
            gaps.append(max(0, s2 - e1))
    if gaps:
        avg_gap = sum(gaps) / len(gaps)
        f_gap = max(0.0, 1 - avg_gap / 180)  # 180 دقيقة = أقصى فجوة تُحتسب
    else:
        f_gap = 1.0  # لا توجد فجوات (يوم واحد لكل محاضرة أو لا تداخل أيام) = محايد أفضل حالة

    # f_morning: فعّال فقط إن طلب الطالب تفضيل الدوام الصباحي؛ غير ذلك محايد
    if prefer_morning and start_times_minutes:
        avg_start = sum(start_times_minutes) / len(start_times_minutes)
        f_morning = max(0.0, 1 - max(0, avg_start - 480) / 240)  # 240 دقيقة نافذة حتى الساعة 12
    else:
        f_morning = 1.0

    # f_instr: نسبة المقررات التي طلب الطالب لها دكتوراً معيناً وتحقق ذلك فعلاً
    if preferred_instructors:
        matches = sum(
            1 for code, wanted in preferred_instructors.items()
            if code in schedule and schedule[code].doctor_name == wanted
        )
        f_instr = matches / len(preferred_instructors)
    else:
        f_instr = 1.0

    score = 100 * (
        weights["days"] * f_days
        + weights["gap"] * f_gap
        + weights["morning"] * f_morning
        + weights["instructor"] * f_instr
    )
    return score