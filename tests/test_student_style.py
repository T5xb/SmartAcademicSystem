from src.student_style import (
    expand_query,
    formal_terms,
    greeting_prefix,
    small_talk_reply,
)


def test_dialect_terms_map_to_document_wording():
    assert "الاختبار الفصلي" in formal_terms("تغيبت عن الميد")
    assert "حذف مقرر دراسي" in formal_terms("اقدر احذف ماده؟")
    assert "النسبة الموزونة المركبة وشروط التحويل" in formal_terms("كم الموزونه؟")
    assert "الخطة الدراسية" in formal_terms("خطه نظم")


def test_expand_query_keeps_the_question_first():
    q = "تغيبت عن الميد وش اسوي؟"
    expanded = expand_query(q)
    assert expanded.startswith(q)
    assert "الاختبار الفصلي" in expanded


def test_bare_keyword_becomes_a_request():
    assert expand_query("تقويم").startswith("أعطني معلومات عن: تقويم")


def test_question_without_dialect_is_unchanged():
    q = "ما هي رؤية الجامعة؟"
    assert expand_query(q) == q


def test_greeting_is_returned():
    assert greeting_prefix("السلام عليكم كم ساعة الغياب؟").startswith("وعليكم السلام")
    assert greeting_prefix("كم ساعة الغياب؟") == ""


def test_small_talk_only_for_pure_greeting_or_thanks():
    assert small_talk_reply("السلام عليكم").startswith("وعليكم السلام")
    assert "يعافيك" in small_talk_reply("يعطيك العافيه 🤍")
    assert "يعافيك" in small_talk_reply("شكراً")
    assert small_talk_reply("السلام عليكم وش شروط التحويل؟") is None
    assert small_talk_reply("شكرا، طيب متى الحذف؟") is None


def test_greeting_not_doubled_when_model_also_greets():
    from src.student_style import with_greeting

    out = with_greeting("السلام عليكم كم الغياب؟", "وعليكم السلام، الغياب المسموح 25%.")
    assert out.count("وعليكم السلام") == 1
    assert out.endswith("الغياب المسموح 25%.")
    assert with_greeting("كم الغياب؟", "الغياب 25%.") == "الغياب 25%."


def test_add_drop_question_reaches_calendar_wording():
    terms = formal_terms("متى الحذف والاضافه؟")
    assert "التسجيل الإلحاقي والحذف والإضافة" in terms
    assert "مواعيد التقويم الدراسي" in terms
