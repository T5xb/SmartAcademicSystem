"""
What to do when a question is unclear or has no answer in the documents.

Instead of sending the student straight to the advising office, the bot
asks for a clearer question a couple of times, the way the group's
moderators do ("وضّح أكثر، وش اللي صار؟"). Only when that still leads
nowhere does it suggest opening a ticket with academic advising.

The attempt count comes from the conversation the chat page sends with
each question (its last few messages), so nothing is stored on the server.
A clarification reply carries CLARIFY_MARK, which is how a later request
recognises it in that history.
"""

import os
import re

from src.student_style import formal_terms, small_talk_reply

# Clarifying questions before the ticket suggestion.
MAX_CLARIFY_ATTEMPTS = int(os.getenv("MAX_CLARIFY_ATTEMPTS", "2"))

# Link to the advising ticket page. Empty for now: the message stays text
# only until the page exists, then setting TICKET_URL in src/.env adds it.
TICKET_URL = os.getenv("TICKET_URL", "").strip()

CLARIFY_MARK = "🤔|"
TICKET_MARK = "🎫|"

# History the API accepts per request; older messages don't matter here.
MAX_HISTORY = 12

# Words that say "I have a question" without saying what it is: "عندي
# مشكلة"، "ممكن سؤال"، "احد يعرف؟". What is left after removing them (and
# greetings) is the actual topic, if any.
_FILLER_WORDS = set("""
عندي عندنا لدي لدينا ابي أبي ابغى أبغى ابغا ودي بغيت اريد أريد
ممكن لو سمحت سمحتوا تكفى تكفون الله يعافيك يعطيك العافية العافيه
سؤال سوال سؤالي استفسار استفسارات استفسر اسأل اسال اسئلة أسئلة
مشكلة مشكله مشكلتي مشاكل ساعدوني ساعدني مساعدة مساعده ضروري عاجل
احد أحد يعرف يدري يا شباب بنات جماعة جماعه اخوان السلام عليكم
ورحمة ورحمه وبركاته هلا مرحبا اعرف أعرف اقول أقول سؤالين شي شيء
في عن بخصوص طيب اوكي ok بس
""".split())
_QUESTION_WORD_RE = re.compile(
    r"\b(كم|متى|وش|ايش|إيش|كيف|هل|ليش|لماذا|ماذا|وين|أين|اين|مين)\b"
)


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", text)


def is_vague(message: str) -> bool:
    """
    True when the message says there is a question but not what it is,
    e.g. "عندي مشكلة" or "ممكن سؤال؟". Those skip the search entirely: a
    lookup on them can only return noise.
    """
    if formal_terms(message):
        return False  # names a topic (تحويل، حذف، غياب...) -> searchable
    words = _words(message)
    content = [w for w in words if w not in _FILLER_WORDS]
    if not content:
        return True  # only "I have a question", emoji or punctuation
    if len(content) == 1:
        # "عندي مشكلة بالتسجيل", "الجامعة": one bare word, no question.
        return len(words) > 1 or not _QUESTION_WORD_RE.search(message)
    return False


def _clean_history(history) -> list[dict]:
    """Keep well-formed {role, text} items, newest last."""
    items = []
    for m in (history or [])[-MAX_HISTORY:]:
        role = (m.get("role") if isinstance(m, dict) else getattr(m, "role", "")) or ""
        text = (m.get("text") if isinstance(m, dict) else getattr(m, "text", "")) or ""
        if role in ("user", "bot") and text.strip():
            items.append({"role": role, "text": text})
    return items


def clarify_streak(history) -> int:
    """How many clarifying questions in a row the bot has just asked."""
    streak = 0
    for m in reversed(_clean_history(history)):
        if m["role"] != "bot":
            continue
        if CLARIFY_MARK in m["text"]:
            streak += 1
        else:
            break
    return streak


def pending_question(history, message: str) -> str:
    """
    The student's question so far: what they wrote since the bot started
    asking for clarification, plus this message. "عندي مشكلة بالتسجيل" then
    "ما قدرت انزل مادة" is searched as one question.
    """
    items = _clean_history(history)
    parts: list[str] = []
    for m in reversed(items):
        if m["role"] == "bot":
            if CLARIFY_MARK in m["text"]:
                continue
            break
        if not small_talk_reply(m["text"]):
            parts.insert(0, m["text"].strip())
    if clarify_streak(items) == 0:
        return message.strip()
    parts.append(message.strip())
    return "\n".join(parts)


TOPIC_HINTS = "تحويل، حذف أو اعتذار، غياب، تسجيل وجدول، خطة دراسية ومتطلبات، معدل وإنذار، تقويم ومواعيد"


def clarify_reply(message: str, attempt: int) -> str:
    """A short clarifying question; the second one gives example questions."""
    if attempt <= 1:
        terms = formal_terms(message)
        if terms:
            return (
                f"{CLARIFY_MARK} ودي أساعدك، بس أبي أفهم سؤالك أكثر 🙏\n"
                f"سؤالك عن «{terms[0]}»؟ وضّح لي وش اللي صار معك بالضبط أو وش تبي تعرف عنه."
            )
        return (
            f"{CLARIFY_MARK} ودي أساعدك، بس ما وضح لي سؤالك 🙏\n"
            f"وش الموضوع بالضبط؟ مثلًا: {TOPIC_HINTS}.\n"
            "واكتب لي وش اللي صار معك أو وش تبي تعرف."
        )
    return (
        f"{CLARIFY_MARK} للحين ما لقيت جواب واضح، خلنا نجرب مرة ثانية\n"
        "اكتب سؤالك بجملة كاملة فيها اسم الإجراء أو المقرر، مثل:\n"
        "◦ متى آخر يوم للحذف؟\n"
        "◦ وش شروط التحويل من نظم لعلوم الحاسب؟\n"
        "◦ كم نسبة الغياب اللي تحرمني من الاختبار؟"
    )


def ticket_reply() -> str:
    """After the clarifying attempts: open a ticket with academic advising."""
    lines = [
        f"{TICKET_MARK} ما قدرت أوصل لجواب أكيد لسؤالك من الأنظمة واللوائح اللي عندي",
        "تقدر تفتح تذكرة (تيكت) على الإرشاد الأكاديمي وتكتب فيها مشكلتك بالتفصيل، "
        "وبيتواصلون معك بخصوصها إن شاء الله.",
    ]
    if TICKET_URL:
        lines.append(f"[🎫 فتح تذكرة على الإرشاد الأكاديمي]({TICKET_URL})")
    return "\n".join(lines)


def unanswered_reply(message: str, history) -> str:
    """Clarify again, or suggest a ticket once the attempts are used up."""
    attempt = clarify_streak(history) + 1
    if attempt > MAX_CLARIFY_ATTEMPTS:
        return ticket_reply()
    return clarify_reply(message, attempt)
