"""
How students actually ask, and how the reply should sound.

Built from a study of the College of Computer and Information Sciences
Telegram group (about 25k messages, July-October 2026): students write in
Saudi dialect with short forms ("ميد", "احذف", "موزونة", "خطه نظم"), often
send a bare keyword ("تقويم", "خطة"), and open with a greeting. The group's
auto-answer bot replies with a short titled card (an emoji marker, "◦"
bullets, a link), and the human moderators reply briefly, return the
greeting first, and answer in one or two lines.

This module does three things before and after the RAG call:
1. expand_query: adds the formal terms the official documents use, so a
   dialect question still retrieves the right article.
2. small_talk_reply: answers a bare greeting or thanks without a model call.
3. greeting_prefix: returns the greeting when the student opened with one.

No student text is stored here; the examples are paraphrased.
"""

import re

# Dialect / short form (regex) -> the wording the official documents use.
# Order does not matter; every matching entry adds its terms once.
GLOSSARY: list[tuple[str, str]] = [
    (r"ميد|ميدترم|منتصف\s*الفصل|الاختبار\s*الفصلي", "الاختبار الفصلي"),
    (r"فاينل|النهائي", "الاختبار النهائي"),
    (r"كويز", "الاختبارات القصيرة وأعمال الفصل"),
    (r"\bترم\b|الترم|سمستر|الفصل\s*الجاي", "الفصل الدراسي"),
    (r"صيفي|الصيفي", "الفصل الصيفي"),
    (r"احذف|حذف|انحذف", "حذف مقرر دراسي"),
    (r"اعتذر|اعتذار|اجل\s*الترم|أجل\s*الترم|تأجيل", "الاعتذار عن الدراسة وتأجيلها"),
    (r"الحاقي|إلحاقي|اضاف[هة]|إضاف[هة]|انزل\s*ماد", "التسجيل الإلحاقي والحذف والإضافة"),
    (r"شعب[هة]?|الشعب", "شعب المقررات والجدول الدراسي"),
    (r"جدول", "الجدول الدراسي وتسجيل المقررات"),
    (r"غياب|غبت|تغيبت|حرمان|محروم", "الغياب والحرمان من دخول الاختبار"),
    (r"عذر|اعذار|أعذار|صحتي|تقرير\s*طبي", "قبول العذر وأداء اختبار بديل"),
    (r"تحويل|احول|أحول|حولت|محول", "التحويل بين الكليات والأقسام"),
    (r"موزون[هة]|النسب[هة]?\s*المركب[هة]|نسب\s*التحويل", "النسبة الموزونة المركبة وشروط التحويل"),
    (r"خط[هة]|الخط[هة]|خطط", "الخطة الدراسية"),
    (r"متطلب|متطلبات", "المتطلبات السابقة ومتطلبات الخطة"),
    (r"الحر[هة]|حر[هة]", "المقررات الحرة"),
    (r"معدل|تراكمي|فصلي\s*المعدل|GPA", "المعدل التراكمي"),
    (r"انذار|إنذار", "الإنذار الأكاديمي"),
    (r"فصل\s*من\s*الجامع[هة]|طي\s*قيد|انطوى\s*قيدي|مطوي", "طي القيد والفصل من الجامعة"),
    (r"معادل[هة]|اعادل|أعادل|تتعادل", "معادلة المقررات"),
    (r"مكاف[أائ][ةه]", "المكافأة الشهرية للطلاب"),
    (r"تقويم|متى|اجاز[هة]|إجاز[هة]", "مواعيد التقويم الدراسي"),
    (r"الارقام\s*المرجعي[هة]|الأرقام\s*المرجعي[هة]", "الأرقام المرجعية للمقررات"),
    (r"تدريب|كوب|coop", "التدريب التعاوني الميداني"),
    (r"مرتب[هة]\s*الشرف|شرف", "مرتبة الشرف"),
    (r"مستجد|اول\s*سن[هة]|أول\s*سن[هة]|سن[هة]\s*أولى", "الطلاب المستجدون والسنة الأولى المشتركة"),
    (r"خريج|تخرج", "متطلبات التخرج"),
    (r"زائر", "الطالب الزائر"),
    (r"ارشاد|إرشاد|مرشد", "الإرشاد الأكاديمي"),
    (r"اعاد[هة]\s*ماد|أعيد|اعيد", "إعادة دراسة المقرر"),
    (r"متطلب\s*(ل|لـ)?\s*(ايش|إيش|وش|ماذا)|يفتح\s*(لي)?\s*(ايش|وش)|يقفل", "المتطلب السابق للمقررات التالية"),
    # Course nicknames -> official Arabic name, code and English name, so the
    # question lands on the plan / syllabus page of that course.
    (r"برمج[هة]\s*(1|١|وحد[هة])\b|مقدم[هة]\s*برمج", "مقدمة في برمجة الحاسب عال 1140 Introduction to Computer Programming"),
    (r"برمج[هة]\s*(2|٢)\b|شيئي[هة]|اوبجكت|object", "البرمجة الشيئية عال 1241 Object-Oriented Programming"),
    (r"تراكيب\s*(ال)?بيانات|داتا\s*ستركتشر|data\s*structure", "تراكيب البيانات عال 1242 Data Structures"),
    (r"تراكيب\s*محدد[هة]|ديسكريت|discrete", "تراكيب محددة عال 1100 Discrete Structures"),
    (r"تفاضل|كالكولس|calculus", "حساب التفاضل والتكامل التطبيقي ريض 1112 Applied Calculus"),
    (r"فيزياء|فيز", "الفيزياء العامة فيز 1103 والفيزياء التطبيقية فيز 1104"),
    (r"حوسب[هة]", "أساسيات الحوسبة والأخلاقيات عال 1111 Computing Fundamentals and Ethics"),
    (r"قواعد\s*(ال)?بيانات|داتابيس|database", "مبادئ قواعد البيانات Database"),
    (r"خوارزمي", "تصميم وتحليل الخوارزميات Algorithms"),
    (r"شبكات", "شبكات الحاسب Computer Networks"),
    (r"(انظم[هة]|أنظم[هة])\s*(ال)?تشغيل", "أنظمة التشغيل Operating Systems"),
    (r"عمار[هة]", "عمارة الحاسب Computer Architecture"),
    (r"منطق\s*رقمي|ديجتال", "تصميم المنطق الرقمي Digital Logic Design"),
    (r"هندس[هة]\s*(ال)?برمجيات|سوفتوير", "هندسة البرمجيات Software Engineering"),
    (r"جبر\s*خطي|لينير", "الجبر الخطي ريض 1227 Linear Algebra"),
    (r"احصاء|إحصاء|احتمالات", "مقدمة في الاحتمالات والإحصاء احص 1011"),
    (r"ذكاء\s*اصطناعي|\bai\b", "الذكاء الاصطناعي Artificial Intelligence"),
    (r"مشروع\s*(ال)?تخرج|جراد", "مشروع التخرج Graduation Project"),
    (r"المواد\s*(ال)?حر[هة]|مقرر\s*حر|الحرة", "المقررات الجامعية الحرة وآلية اختيار المتطلبات الجامعية"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), terms) for p, terms in GLOSSARY]

_GREETING_RE = re.compile(r"^\s*(ال)?سلام\s*(عليكم|عليكم\s*ورحم[هة]\s*الله(\s*وبركاته)?)?")
_THANKS_RE = re.compile(
    r"^\s*(شكرا|شكراً|مشكور[ةه]?|يعطيك\s*العافي[هة]|الله\s*يعطيك\s*العافي[هة]|"
    r"جزاك\s*الله\s*خير[اً]?|تسلم|ثانكس|thanks?)\b",
    re.IGNORECASE,
)
# Whatever is left after removing greetings, thanks, emoji and punctuation.
_FILLER_RE = re.compile(
    r"(ال)?سلام|عليكم|ورحم[هة]|الله|وبركاته|شكرا|شكراً|مشكور[ةه]?|يعطيك|العافي[هة]|"
    r"جزاك|خير[اً]?|تسلم|ثانكس|thanks?|يا\s*(شباب|بنات|اخوان|جماعه|جماعة)|"
    r"[^\w\s]|_",
    re.IGNORECASE,
)

GREETING_REPLY = "وعليكم السلام ورحمة الله وبركاته"


def formal_terms(message: str) -> list[str]:
    """The official-document terms that match the student's wording."""
    terms: list[str] = []
    for pattern, term in _COMPILED:
        if pattern.search(message) and term not in terms:
            terms.append(term)
    return terms


def expand_query(message: str) -> str:
    """
    The text sent to retrieval and to the answer prompt.

    The student's own words stay first (the model answers what was asked);
    the matching formal terms follow so the embedding lands on the right
    article. A bare keyword ("تقويم") becomes an explicit request, like the
    group bot's keyword replies.
    """
    message = message.strip()
    terms = formal_terms(message)
    words = re.findall(r"\w+", message)
    is_bare_keyword = len(words) <= 3 and not re.search(r"[؟?]", message)
    if is_bare_keyword:
        message = f"أعطني معلومات عن: {message}"
    if not terms:
        return message
    return f"{message}\n(المقصود بالمصطلحات الرسمية: {'، '.join(terms)})"


def opens_with_greeting(message: str) -> bool:
    return bool(_GREETING_RE.match(message))


def greeting_prefix(message: str) -> str:
    """Return the greeting first, the way the group's moderators do."""
    return f"{GREETING_REPLY} 🌷\n\n" if opens_with_greeting(message) else ""


_ANSWER_GREETING_RE = re.compile(r"^\s*وعليكم\s+السلام[^\n،,.:]*[،,.:]?\s*")


def with_greeting(message: str, answer: str) -> str:
    """Put the greeting in front once, even if the model already greeted."""
    prefix = greeting_prefix(message)
    if not prefix:
        return answer
    return prefix + _ANSWER_GREETING_RE.sub("", answer, count=1)


def small_talk_reply(message: str) -> str | None:
    """
    A reply for a message that is only a greeting or a thanks, else None.

    Those messages have nothing to retrieve; sending them through RAG ends
    in the "no answer in the documents" message, which reads as rude.
    """
    if _FILLER_RE.sub(" ", message).strip():
        return None
    if _THANKS_RE.match(message):
        return "الله يعافيك 🤍 إذا عندك أي سؤال ثاني عن الدراسة أو الأنظمة، أنا حاضر."
    if opens_with_greeting(message):
        return (
            f"{GREETING_REPLY} 🌷\n"
            "أنا مساعد الإرشاد الأكاديمي لكلية الحاسب. اسألني عن التحويل، الحذف والاعتذار، "
            "الغياب، الخطط الدراسية، المعدل، أو التقويم الدراسي."
        )
    return None
