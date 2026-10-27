# -*- coding: utf-8 -*-
"""
اختبار انحدار لـ csp_scheduler.py: يغطي node consistency (H5/H6/H7)، التعارض
(H2/H3)، forward checking، وتشخيص سبب الفشل — بمقررات وهمية بسيطة بدل الاعتماد
على course_data.py الكامل، حتى يبقى الاختبار سريعاً ومعزولاً عن تغييرات الخطة.

الاستخدام:
    .venv/Scripts/python.exe -m tests.test_csp_scheduler
"""
import sys
from src.scheduling.models import Student, Course, CourseSection, TimeSlot
from src.scheduling.csp_scheduler import StudentCSPScheduler, evaluate_schedule

ts_sun_0800 = TimeSlot(1, "08:00", "09:15", "الأحد 08:00-09:15", days=["الأحد"])
ts_sun_1000 = TimeSlot(2, "10:00", "11:15", "الأحد 10:00-11:15", days=["الأحد"])
ts_mon_0800 = TimeSlot(3, "08:00", "09:15", "الاثنين 08:00-09:15", days=["الاثنين"])


def check(label, actual, expected):
    ok = actual == expected
    print(("✅" if ok else "❌") + f" {label}: actual={actual!r} expected={expected!r}")
    return ok


def main():
    all_ok = True

    # --- 1) الحالة العادية: مقرران بلا تعارض، يجب إيجاد حل واحد على الأقل ---
    course_a = Course("A", "مقرر أ", 3, [], [
        CourseSection("A1", "A", [ts_sun_0800], "د. أحمد"),
        CourseSection("A2", "A", [ts_sun_1000], "د. سارة"),
    ])
    course_b = Course("B", "مقرر ب", 3, [], [
        CourseSection("B1", "B", [ts_mon_0800], "د. خالد"),
    ])
    student = Student("s1", [], [course_a, course_b])
    scheduler = StudentCSPScheduler(student)
    found = scheduler.solve_all(limit=5)
    all_ok &= check("basic case: a solution is found", found, True)
    all_ok &= check("basic case: no failure_reason when solved", scheduler.failure_reason, None)

    # --- 2) H5 (سعة المقاعد): شعبة ممتلئة يجب أن تُستبعد من النطاق منذ البداية ---
    full_section = CourseSection("A1", "A", [ts_sun_0800], "د. أحمد", capacity=30, enrolled=30)
    open_section = CourseSection("A2", "A", [ts_sun_1000], "د. سارة", capacity=30, enrolled=29)
    course_a_seats = Course("A", "مقرر أ", 3, [], [full_section, open_section])
    student2 = Student("s2", [], [course_a_seats])
    scheduler2 = StudentCSPScheduler(student2)
    all_ok &= check("H5: full section excluded from initial domain",
                     [s.section_id for s in scheduler2.domains["A"]], ["A2"])

    # --- 3) H2 (تعارض وقت) + forward checking: مقرران بشعبة وحيدة متعارضة زمنياً => فشل ---
    course_c = Course("C", "مقرر ج", 3, [], [CourseSection("C1", "C", [ts_sun_0800], "د. منى")])
    course_d = Course("D", "مقرر د", 3, [], [CourseSection("D1", "D", [ts_sun_0800], "د. ريم")])
    student3 = Student("s3", [], [course_c, course_d])
    scheduler3 = StudentCSPScheduler(student3)
    found3 = scheduler3.solve_all(limit=5)
    all_ok &= check("conflict case: no solution found", found3, False)
    all_ok &= check("conflict case: failure_reason is set", scheduler3.failure_reason is not None, True)

    # --- 4) H6 (التثبيت) + H7 (نافذة الوقت): يُطبَّقان في النطاق الابتدائي ---
    course_e = Course("E", "مقرر هـ", 3, [], [
        CourseSection("E1", "E", [ts_sun_0800], "د. فهد"),
        CourseSection("E2", "E", [ts_mon_0800], "د. نورة"),
    ])
    student4 = Student("s4", [], [course_e])
    scheduler4 = StudentCSPScheduler(student4, pinned_sections={"E": "E2"})
    all_ok &= check("H6: pinned section is the only one in the domain",
                     [s.section_id for s in scheduler4.domains["E"]], ["E2"])

    scheduler5 = StudentCSPScheduler(student4, off_days=["الاثنين"])
    all_ok &= check("H7: off-day section excluded from the domain",
                     [s.section_id for s in scheduler5.domains["E"]], ["E1"])

    # --- 5) evaluate_schedule: لا ينهار مع/بدون preferred_instructors، والقيمة ضمن 0-100 ---
    scheduler.solve_all(limit=5)
    sched = scheduler.get_all_schedules()[0]
    score_plain = evaluate_schedule(sched)
    score_pref = evaluate_schedule(sched, preferred_instructors={"A": "د. أحمد"})
    all_ok &= check("evaluate_schedule: plain score in range", 0 <= score_plain <= 100, True)
    all_ok &= check("evaluate_schedule: with preferred_instructors in range", 0 <= score_pref <= 100, True)

    print()
    if all_ok:
        print("✅ كل الفحوصات نجحت — csp_scheduler.py سليم.")
    else:
        print("❌ بعض الفحوصات فشلت — راجع الفروقات أعلاه قبل نشر التعديل.")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
