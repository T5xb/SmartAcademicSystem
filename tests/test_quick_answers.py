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
