from datetime import date

from src.quick_answers import date_reply, file_reply, load_calendar

TODAY = date(2026, 10, 27)
EVENTS = load_calendar()


def ask(q):
    return date_reply(q, TODAY, EVENTS)


def test_calendar_is_parsed():
    titles = [e.title for e in EVENTS]
    assert len(EVENTS) >= 30
    assert any("بداية الاختبارات النهائية للفصل الدراسي الأول" in t for t in titles)


def test_withdrawal_open_now_shows_end_and_countdown():
    out = ask("متى ينتهي الحذف؟")
    assert "متاح الآن" in out and "12/12/2026" in out and "باقي 46 يوم" in out
    assert "/data/" not in out and "📄" not in out  # a date, not a file


def test_next_holiday_is_the_autumn_break():
    out = ask("متى الاجازة القادمة؟")
    assert "الخريف" in out and "19/11/2026" in out


def test_add_drop_means_registration_window():
    assert "تسجيل المقررات" in ask("متى الحذف والاضافه؟")


def test_second_semester_is_respected():
    assert "17/01/2027" in ask("متى يبدأ الترم الثاني؟")


def test_no_date_word_no_date_reply():
    assert ask("وش شروط الحذف") is None


def test_full_plan_request_returns_the_file():
    out = file_reply("ابي خطة علوم الحاسب")
    assert "[📄 خطة علوم الحاسب](/data/" in out
    assert "تقنية" not in out


def test_information_department_plans_do_not_also_send_cs():
    for q, name in [("خطة تقنية المعلومات", "تقنية المعلومات"), ("ابي خطة نظم المعلومات", "نظم المعلومات")]:
        out = file_reply(q)
        assert out.count("[📄") == 1 and f"خطة {name}" in out


def test_plan_without_department_lists_all_three():
    out = file_reply("خطة")
    assert out.count("[📄") == 3


def test_calendar_request_returns_the_calendar_file():
    for q in ["التقويم الدراسي", "ابي التقويم الدراسي هذا الترم", "التقويم الدراسي هذي السنة"]:
        assert "Calendar_1448.pdf" in file_reply(q)


def test_question_inside_the_plan_is_not_a_file_request():
    assert file_reply("كم ساعه خطة نظم؟") is None
    assert file_reply("خطة علوم حاسب وش متطلب برمجة 2") is None


# ------------------------------------------------------------ prerequisites

from src.quick_answers import load_cs_plan, prereq_reply  # noqa: E402

PLAN = load_cs_plan()


def test_plan_is_parsed():
    assert PLAN["عال 1360"].name == "الذكاء الاصطناعي"
    assert PLAN["عال 1111"].prereq == "لا يوجد"
    assert "عال 1290" not in PLAN  # diploma section is skipped


def test_dialect_question_by_name():
    out = prereq_reply("وش متطلب مقرر الذكاء الاصطناعي؟", PLAN)
    assert "عال 1312" in out and "ريض 1227" in out and "احص 1011" in out


def test_nickname_maps_to_the_course():
    out = prereq_reply("وش متطلب الشبكات؟", PLAN)
    assert "عال 1330" in out and "عال 1322" in out


def test_written_code():
    assert "عال 1241" in prereq_reply("متطلب cs 1242", PLAN)


def test_longest_official_name_wins():
    out = prereq_reply("وش متطلب قواعد البيانات المتقدمة؟", PLAN)
    assert "عال 1471" in out and "عال 1370 (مبادئ" not in out.split("\n")[0]


def test_no_prerequisite():
    assert "ما له متطلب سابق" in prereq_reply("متطلب أساسيات الحوسبة والأخلاقيات؟", PLAN)


def test_other_questions_go_to_search():
    assert prereq_reply("وش متطلبات التخرج؟", PLAN) is None
    assert prereq_reply("متطلب الشبكات في تقنية المعلومات؟", PLAN) is None
    assert prereq_reply("الذكاء الاصطناعي متطلب لإيش؟", PLAN) is None
