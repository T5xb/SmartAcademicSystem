"""Polite crawler for the public IMSIU website (imamu.edu.sa).

Collects student-facing documents and pages (regulations, calendars, study
plans, admission/registration rules, forms, FAQs, ...) into
raw_university_docs/ for the RAG academic-advising chatbot.

Three sources are handled:
  1. Main site (Next.js, imamu.edu.sa/ar/...): visible text + the page data
     embedded in the `self.__next_f` payload (e.g. FAQ answers).
  2. Regulations platform (imamu.edu.sa/laws): the public search/details JSON
     handler used by the page itself. Only regulations in force ("ساري") that
     concern students are kept. Regulation *files* need a login, so they are
     not downloaded; the full text shown publicly on the details page is saved.
  3. Deanship / college sites (units.imamu.edu.sa, SharePoint): server-rendered
     pages + each site's public menu handler, plus linked documents.

Rules: robots.txt is obeyed (with * and $ wildcards), >=1 s between requests,
no login pages or portals, depth and page caps, no media.

Usage:
    python scripts/crawl_university.py [--out raw_university_docs]
        [--max-pages 3000] [--max-depth 4] [--delay 1.0] [--skip-laws]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup, Comment, Doctype, ProcessingInstruction

try:
    from pypdf import PdfReader
except ImportError:  # optional: only used to flag scanned PDFs
    PdfReader = None

UA = ("SmartAcademicSystem-Crawler/1.0 (student graduation project; "
      "collects public academic regulations for an advising chatbot)")

DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}
MEDIA_EXT = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp", ".tif", ".tiff",
             ".mp4", ".mp3", ".avi", ".mov", ".wmv", ".wav", ".m4a", ".webm", ".zip", ".rar",
             ".7z", ".css", ".js", ".mjs", ".xml", ".json", ".txt", ".exe", ".msi", ".apk", ".avif"}

ALLOWED_HOSTS = {"imamu.edu.sa", "www.imamu.edu.sa", "units.imamu.edu.sa", "content.imamu.edu.sa"}
# Portals / login systems / file stores that need a login: never fetched.
DENY_HOSTS = {"srs", "bstss", "academicadvising", "morasel", "epm", "alumni", "crm", "awareness",
              "internshipunit", "miraat", "s", "fdf", "mail", "owa", "lms", "sis", "portal", "sso",
              "login", "adfs", "jobs", "eservices", "betaportal"}

# Main-site sections that are not useful for advising.
EXCLUDE_URL = re.compile(
    r"/(en|fr)(/|$)|/university-news|/events|/conferences|/hackathons|/jobs|/media-library"
    r"|/press-files|/PressFile|/graduates|/researchers-partners|/sustainability|/contact-us"
    r"|/content/Pages/|/Authenticate\.aspx|/_layouts/15/[^?]*\.aspx|/_catalogs/|/SitePages/"
    r"|/Lists/|/Forms/|/photos?/|/gallery|/videos?/|/media/|/tenders?|/procurement|/vacanc"
    r"|/OrganizationalChart|/ISO9001|/QP\.aspx|PageNotFoundError|/print|/search|/osearch",
    re.I)
EXCLUDE_TITLE = re.compile(
    r"مناقص|منافس|توريد|عقود|وظائف|وظيفة|توظيف|التوظيف|مؤتمر|ملتقى|ندوة|محاضرة عامة|ورشة|"
    r"سيرة ذاتية|السيرة الذاتية|براءة اختراع|مجلة|كرسي|بحوث منشورة|أبحاث|الأخبار|خبر|"
    r"زيارة|تهنئة|يستقبل|يدشن|يرعى|حفل|معرض|المخطط التنظيمي|الهيكل التنظيمي|سياسة الجودة|"
    r"tender|vacanc|conference|news|cv\b|curriculum vitae", re.I)

CATEGORIES = [
    ("faqs", r"الأسئلة الشائعة|الاسئلة الشائعة|أسئلة شائعة|faq"),
    ("academic_calendar", r"التقويم|تقويم|calendar"),
    ("forms", r"نموذج|نماذج|استمارة|form\b|forms"),
    ("graduate_studies", r"الدراسات العليا|دراسات عليا|ماجستير|الماجستير|دكتوراه|الدكتوراه|"
                         r"دبلوم عالي|graduate|postgrad|/GRADUATE"),
    ("fees_and_rewards", r"مكافأة|مكافآت|المكافآت|رسوم|إعانة|الإعانات|سداد|reward|fees"),
    ("course_catalogs", r"توصيف|وصف المقرر|المقررات الدراسية|دليل المقررات|course"),
    ("study_plans", r"خطة|الخطط|خطط|البرامج الأكاديمية|البرامج الدراسية|برنامج|ProgramsLinks|"
                    r"study.?plan|program"),
    ("admission_registration", r"القبول|قبول|التسجيل|تسجيل|التحويل|تحويل|التجسير|تجسير|"
                               r"الطلبة الدوليين|المنح|الانسحاب|الاعتذار|التأجيل|تأجيل|"
                               r"إعادة القيد|طي القيد|الحذف والإضافة|السجل الأكاديمي|"
                               r"الجدول الدراسي|الاختبارات|admission|registration|transfer"),
    ("student_affairs", r"شؤون الطلاب|شؤون الطالب|الطلاب|الطالب|الطالبات|طلاب|سكن|"
                        r"النشاط|الأندية|الإرشاد|إرشاد|عناية|حقوق|واجبات|تأديب|المخالفات|"
                        r"الخريجين|التخرج|student"),
    ("regulations", r"لائحة|اللائحة|لوائح|اللوائح|القواعد التنفيذية|ضوابط|الضوابط|تنظيم|"
                    r"الأنظمة|أنظمة|قواعد|regulation|bylaw|policy|سياسة"),
]
CAT_RE = [(c, re.compile(p, re.I)) for c, p in CATEGORIES]
REG_RE = re.compile(r"لائحة|اللائحة|لوائح|اللوائح|القواعد التنفيذية|ضوابط|الضوابط|قواعد|نظام الدراسة|"
                    r"regulation|bylaw", re.I)
STRONG_RE = re.compile(
    r"لائحة|اللائحة|القواعد|ضوابط|التقويم|الخطط|خطة|توصيف|القبول|التسجيل|التحويل|الانسحاب|"
    r"الاعتذار|تأجيل|التأجيل|الأسئلة الشائعة|نموذج|نماذج|مكاف|رسوم|الدراسات العليا|التخرج|"
    r"الإنذار|الفصل الأكاديمي|المعدل|الاختبارات|شؤون الطلاب|حقوق الطالب|السكن|المنح|الطلبة الدوليين|"
    r"التجسير|الدبلوم|البرامج|المقررات|الإرشاد الأكاديمي|عمادة القبول|admission|regulation|calendar|"
    r"study plan|faq|ProgramsLinks|TRANSFER|Scholarship|TJSEER", re.I)
WEAK_RE = re.compile(r"طالب|طلاب|الطالب|الطلاب|الطالبات|الدراسة|دراسي|الكلية|كلية|القسم|الأقسام|"
                     r"الخدمات|عمادة|دليل|إرشادات|student|college|department|deanship", re.I)

# Main-site seed pages (Arabic).
SEEDS = [
    "https://imamu.edu.sa/ar/university-acceptance",
    "https://imamu.edu.sa/ar/faqs",
    "https://imamu.edu.sa/ar/about-university/university-faqs",
    "https://imamu.edu.sa/ar/academic-programs",
    "https://imamu.edu.sa/ar/colleges-and-institutes",
    "https://imamu.edu.sa/ar/deanships",
    "https://imamu.edu.sa/ar/services",
    "https://imamu.edu.sa/ar/document-library",
    "https://imamu.edu.sa/ar/systems",
    "https://imamu.edu.sa/ar/electronic-consultation",
    "https://imamu.edu.sa/ar/facilities",
    "https://imamu.edu.sa/ar/about-university/agencies",
    "https://units.imamu.edu.sa/deanships/admission/Pages/admission/default.aspx",
    "https://units.imamu.edu.sa/deanships/admission/programs/Pages/default.aspx",
    "https://units.imamu.edu.sa/deanships/GRADUATE/Pages/g20/101.aspx",
]
# SharePoint unit sites whose public menu handler is read.
UNIT_SITES = [
    "https://units.imamu.edu.sa/deanships/admission",
    "https://units.imamu.edu.sa/deanships/sa",
    "https://units.imamu.edu.sa/deanships/GRADUATE",
    "https://units.imamu.edu.sa/deanships/sr",
]
# --focus: College of Computer and Information Sciences, Admission & Registration deanship,
# academic calendar, study plans, FAQs and the core regulations only.
CCIS = "https://units.imamu.edu.sa/colleges/ComputerAndInformation"
FOCUS_UNIT_SITES = [CCIS, "https://units.imamu.edu.sa/deanships/admission"]
FOCUS_SEEDS = [
    CCIS + "/Pages/default.aspx",
    CCIS + "/profile",
    CCIS + "/academic_department",
    "https://units.imamu.edu.sa/deanships/admission/Pages/admission/default.aspx",
    "https://units.imamu.edu.sa/deanships/admission/programs/Pages/default.aspx",
    "https://units.imamu.edu.sa/deanships/admission/Pages/Questions.aspx",
    "https://units.imamu.edu.sa/deanships/admission/Pages/plans.aspx",
    "https://units.imamu.edu.sa/deanships/admission/Pages/achievement.aspx",
    "https://units.imamu.edu.sa/deanships/admission/news/Pages/news120.aspx",
    "https://units.imamu.edu.sa/vrectorate/VR/StudentGuide/Pages/default.aspx",
    "https://imamu.edu.sa/ar/university-acceptance",
    "https://imamu.edu.sa/ar/faqs",
    "https://imamu.edu.sa/ar/about-university/university-faqs",
]
FOCUS_PREFIXES = (
    "https://units.imamu.edu.sa/colleges/computerandinformation",
    "https://units.imamu.edu.sa/deanships/admission",
    "https://units.imamu.edu.sa/vrectorate/vr/studentguide",
    "https://imamu.edu.sa/ar/university-acceptance",
    "https://imamu.edu.sa/ar/faqs",
    "https://imamu.edu.sa/ar/about-university/university-faqs",
)
FOCUS_LAWS = re.compile(
    r"الدراسة والاختبارات|الدراسة الجامعية|المرحلة الجامعية|القبول|التسجيل|التحويل|المكافآت|مكافآت|"
    r"التأديب|تأديب|حقوق|الدراسات العليا|للدراسات العليا|التدريب التعاوني|التدريب الميداني|الامتياز|الخطط الدراسية|"
    r"المقررات|الإرشاد الأكاديمي|التقويم|الاختبارات|الطلاب|الطلبة|الطالب|السكن الجامعي|الزائر|المنح")


def in_focus(url: str) -> bool:
    u = unquote(url).lower()
    return u.startswith(FOCUS_PREFIXES) or "تقويم" in u or "calendar" in u


BASELINE_PAGE ="https://imamu.edu.sa/ar/contact-us"  # used to learn header/footer boilerplate

LAWS_HANDLER = "https://imamu.edu.sa/laws/_layouts/15/2016/Laws/Handlers/LawsGeneralHandler.ashx"
LAWS_DETAILS = "https://imamu.edu.sa/Laws/Pages/UCDetails.aspx?rid={rid}&flag=true"

ARABIC = re.compile(r"[؀-ۿ]")
GENERIC_ANCHORS = {"تحميل", "download", "اضغط هنا", "هنا", "من هنا", "رابط", "الملف", "pdf", "PDF",
                   "عرض", "اطلع", "للاطلاع", "تنزيل", "اضغط", "الرابط", "وثيقة البرنامج", "الوثيقة"}
FEEDBACK_CUT = re.compile(r"شكرا على تقييمك|هل أعجبك محتوى الصفحة|الاستفسارات والمقترحات والشكاوى")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- robots.txt
class Robots:
    """Minimal robots.txt with Google-style * / $ wildcards and longest-match wins."""

    def __init__(self, text: str | None):
        self.rules: list[tuple[bool, str, re.Pattern]] = []
        self.delay = 0.0
        if not text or "<html" in text.lower()[:500]:
            return
        active = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = [x.strip() for x in line.split(":", 1)]
            k = k.lower()
            if k == "user-agent":
                active = v == "*"
            elif active and k in ("allow", "disallow") and v:
                pat = "^" + re.escape(v).replace(r"\*", ".*").replace(r"\$", "$")
                if v.startswith("*"):
                    pat = "^/?" + pat[1:]
                self.rules.append((k == "allow", v, re.compile(pat)))
            elif active and k == "crawl-delay":
                try:
                    self.delay = float(v)
                except ValueError:
                    pass

    def allowed(self, path: str) -> bool:
        best = None
        for allow, raw, rx in self.rules:
            if rx.search(path):
                if best is None or len(raw) > len(best[1]) or (len(raw) == len(best[1]) and allow):
                    best = (allow, raw)
        return True if best is None else best[0]


# ---------------------------------------------------------------- helpers
def sanitize(name: str, maxlen: int = 90) -> str:
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name[:maxlen].strip(" .") or "untitled")


def norm_url(url: str) -> str | None:
    try:
        sp = urlsplit(url.strip())
    except ValueError:
        return None
    if sp.scheme not in ("http", "https"):
        return None
    host = (sp.hostname or "").lower()
    path = sp.path or "/"
    q = [(k, v) for k, v in parse_qsl(sp.query, keep_blank_values=True)
         if not k.lower().startswith("utm_") and k.lower() not in ("source",)]
    if host in ("imamu.edu.sa", "www.imamu.edu.sa") and path.startswith("/ar"):
        q = [(k, v) for k, v in q if k in ("tab", "step")]  # Next.js tab state only
    return urlunsplit(("https", host, path, urlencode(q), ""))


def host_ok(host: str) -> bool:
    host = host.lower()
    if host in ALLOWED_HOSTS:
        return True
    if not host.endswith(".imamu.edu.sa"):
        return False
    return host.split(".")[0] not in DENY_HOSTS


def ext_of(url: str) -> str:
    p = unquote(urlsplit(url).path).lower()
    m = re.search(r"\.[a-z0-9]{2,5}$", p)
    return m.group(0) if m else ""


def categorize(*texts: str) -> str:
    blob = " ".join(t for t in texts if t)
    if REG_RE.search(blob) and not re.search(r"نموذج|استمارة", blob):
        # explicit regulations win over generic student words, but not over FAQ/calendar/grad
        for c, rx in CAT_RE[:4]:
            if rx.search(blob):
                return c
        return "regulations"
    for c, rx in CAT_RE:
        if rx.search(blob):
            return c
    return "other"


def score(text: str) -> int:
    s = 3 * len(STRONG_RE.findall(text or "")) + len(WEAK_RE.findall(text or ""))
    if EXCLUDE_TITLE.search(text or ""):
        s -= 6
    return s


# ---------------------------------------------------------------- HTML -> markdown
BLOCK_TAGS = {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "br", "table", "ul", "ol", "dd", "dt", "blockquote"}


def element_to_md(el) -> str:
    out: list[str] = []

    def walk(node):
        name = getattr(node, "name", None)
        if name is None:
            if isinstance(node, (Comment, Doctype, ProcessingInstruction)):
                return  # includes React streaming markers <!--$-->, <!--/$-->
            t = str(node)
            if t.strip():
                out.append(re.sub(r"\s+", " ", t))
            return
        if name in ("script", "style", "noscript", "svg", "button", "form", "nav", "footer",
                    "header", "iframe", "select", "input", "img"):
            return
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            out.append("\n\n" + "#" * min(int(name[1]) + 1, 6) + " ")
        elif name == "li":
            out.append("\n- ")
        elif name == "tr":
            cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in node.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            if cells:
                out.append("\n| " + " | ".join(cells) + " |")
            return
        elif name == "br":
            out.append("\n")
        elif name in BLOCK_TAGS:
            out.append("\n")
        if name == "a" and node.get("href", "").lower().split("?")[0].endswith(tuple(DOC_EXT)):
            txt = node.get_text(" ", strip=True)
            out.append(f" {txt} ({node['href']}) ")
            return
        for ch in node.children:
            walk(ch)
        if name in BLOCK_TAGS:
            out.append("\n")

    walk(el)
    text = "".join(out).replace("​", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_fragment_to_text(s: str) -> str:
    if "<" in s and ">" in s:
        return element_to_md(BeautifulSoup(s, "html.parser"))
    return s.strip()


def drop_repeated_tail(text: str) -> str:
    """The Nizam FullText often repeats the whole regulation; cut where the repeated copy starts."""
    lines = text.split("\n")
    longs = [i for i, x in enumerate(lines) if len(x.strip()) > 60]
    first: dict[str, int] = {}
    for i in longs:
        first.setdefault(lines[i].strip(), i)
    for s in longs[5:]:
        if first[lines[s].strip()] < s and all(first[lines[j].strip()] < s for j in longs if j >= s):
            while s > 0 and len(lines[s - 1].strip()) <= 60:
                s -= 1
            return "\n".join(lines[:s]).rstrip()
    return text


def cut_feedback(text: str) -> str:
    m = FEEDBACK_CUT.search(text)
    return text[:m.start()].rstrip() if m else text


# ---------------------------------------------------------------- Next.js payload
def next_payload(html: str) -> str:
    parts = []
    for m in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", html, re.S):
        try:
            arr = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if len(arr) > 1 and isinstance(arr[1], str):
            parts.append(arr[1])
    return "".join(parts)


JSON_STR = re.compile(r'"((?:[^"\\]|\\.)*)"')


def payload_strings(payload: str) -> list[str]:
    out = []
    for m in JSON_STR.finditer(payload):
        raw = m.group(1)
        if len(raw) < 40 or not ARABIC.search(raw):
            continue
        try:
            s = json.loads('"' + raw + '"')
        except json.JSONDecodeError:
            continue
        if len(ARABIC.findall(s)) < 20 or s.lstrip().startswith(("$", "{", "[", "http", "/")):
            continue
        if "جامعة الإمام محمد بن سعود الإسلامية" in s and len(s) < 90:
            continue
        out.append(s)
    return out


def payload_faq(payload: str) -> list[tuple[str, str]]:
    pairs = []
    for m in re.finditer(r'"questionAr":"((?:[^"\\]|\\.)*)".*?"answerAr":"((?:[^"\\]|\\.)*)"', payload, re.S):
        try:
            q = json.loads('"' + m.group(1) + '"')
            a = json.loads('"' + m.group(2) + '"')
        except json.JSONDecodeError:
            continue
        pairs.append((q.strip(), html_fragment_to_text(a)))
    return pairs


def payload_links(payload: str) -> list[tuple[str, str]]:
    links = []
    for m in re.finditer(r'"(https?://[^"\s]*imamu\.edu\.sa[^"\s]*|/ar/[^"\s]*)"', payload):
        links.append((m.group(1), ""))
    return links


# ---------------------------------------------------------------- crawler
class Crawler:
    def __init__(self, out: Path, max_pages: int, max_depth: int, delay: float, max_docs: int,
                 focus: bool = False):
        self.focus = focus
        self.out = out
        self.max_pages, self.max_depth, self.delay, self.max_docs = max_pages, max_depth, delay, max_docs
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"})
        self.robots: dict[str, Robots] = {}
        self.last_req = 0.0
        self.queue: list = []
        self.seen: set[str] = set()
        self.counter = 0
        self.pages_fetched = 0
        self.docs_fetched = 0
        self.index: list[dict] = []
        self.hashes: dict[str, str] = {}
        self.failures: list[dict] = []
        self.skipped: list[dict] = []
        self.boiler: set[str] = set()
        self.unit_sites_done: set[str] = set()
        self.log = open(out / "_crawl_log.jsonl", "a", encoding="utf-8")

    # -- networking
    def robots_for(self, host: str) -> Robots:
        if host not in self.robots:
            try:
                self.wait()
                r = self.s.get(f"https://{host}/robots.txt", timeout=30)
                self.robots[host] = Robots(r.text if r.status_code == 200 else None)
            except requests.RequestException:
                self.robots[host] = Robots(None)
        return self.robots[host]

    def wait(self):
        delay = max(self.delay, max((r.delay for r in self.robots.values()), default=0.0))
        dt = time.time() - self.last_req
        if dt < delay:
            time.sleep(delay - dt)
        self.last_req = time.time()

    def allowed(self, url: str) -> tuple[bool, str]:
        sp = urlsplit(url)
        if not host_ok(sp.hostname or ""):
            return False, "host not allowed"
        path = sp.path + (("?" + sp.query) if sp.query else "")
        if not self.robots_for(sp.hostname).allowed(path):
            return False, "robots.txt"
        return True, ""

    def get(self, url: str, **kw) -> requests.Response | None:
        ok, why = self.allowed(url)
        if not ok:
            self.skipped.append({"url": url, "reason": why})
            return None
        for attempt in range(3):
            self.wait()
            try:
                r = self.s.get(url, timeout=60, allow_redirects=True, **kw)
                final = urlsplit(r.url)
                if "Authenticate.aspx" in r.url or "login" in final.path.lower() or not host_ok(final.hostname or ""):
                    self.skipped.append({"url": url, "reason": f"redirected to {r.url}"})
                    return None
                if r.status_code == 200:
                    return r
                if r.status_code in (403, 404, 410):
                    self.failures.append({"url": url, "error": f"HTTP {r.status_code}"})
                    return None
            except requests.RequestException as e:
                err = str(e)[:200]
                if attempt == 2:
                    self.failures.append({"url": url, "error": err})
                    return None
            time.sleep(2 * (attempt + 1))
        self.failures.append({"url": url, "error": "gave up after retries"})
        return None

    # -- queue
    def push(self, url: str, depth: int, prio: int, referrer: str = "", anchor: str = ""):
        u = norm_url(url)
        if not u or u in self.seen or depth > self.max_depth:
            return
        e = ext_of(u)
        if e in MEDIA_EXT:
            return
        is_doc = e in DOC_EXT
        if not is_doc and EXCLUDE_URL.search(u):
            return
        if not host_ok(urlsplit(u).hostname or ""):
            return
        if anchor and EXCLUDE_TITLE.search(anchor) and not STRONG_RE.search(anchor):
            return
        if self.focus and not is_doc and not in_focus(u):
            return
        self.seen.add(u)
        self.counter += 1
        heapq.heappush(self.queue, (-prio, depth, self.counter, u, referrer, anchor))

    # -- saving
    def save(self, category: str, name: str, data: bytes, title: str, url: str, referrer: str,
             ftype: str) -> dict | None:
        h = hashlib.sha256(data).hexdigest()
        if h in self.hashes:
            self.log_event("duplicate", url=url, same_as=self.hashes[h])
            return None
        folder = self.out / category
        folder.mkdir(parents=True, exist_ok=True)
        base, ext = (name.rsplit(".", 1) + [""])[:2]
        fname = f"{sanitize(base)}.{ext}" if ext else sanitize(base)
        i = 2
        while (folder / fname).exists():
            fname = f"{sanitize(base)}_{i}.{ext}" if ext else f"{sanitize(base)}_{i}"
            i += 1
        (folder / fname).write_bytes(data)
        self.hashes[h] = f"{category}/{fname}"
        row = {"category": category, "file_name": f"{category}/{fname}", "title": title.strip(),
               "source_url": url, "referring_page": referrer, "file_type": ftype,
               "size_bytes": len(data), "sha256": h, "downloaded_at": now_iso()}
        self.index.append(row)
        self.log_event("saved", **row)
        print(f"[saved] {category}/{fname}  <- {url}", flush=True)
        return row

    def save_md(self, category: str, title: str, url: str, referrer: str, body: str):
        md = f"# {title.strip()}\n\nSource: {url}\nRetrieved: {now_iso()}\n\n---\n\n{body.strip()}\n"
        self.save(category, f"{sanitize(title)}.md", md.encode("utf-8"), title, url, referrer, "md")

    def log_event(self, kind: str, **kw):
        self.log.write(json.dumps({"t": now_iso(), "event": kind, **kw}, ensure_ascii=False) + "\n")
        self.log.flush()

    # -- documents
    def handle_doc(self, url: str, referrer: str, anchor: str, ref_title: str):
        if self.docs_fetched >= self.max_docs:
            self.skipped.append({"url": url, "reason": "doc cap reached"})
            return
        fname = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
        ctx = " ".join([anchor, fname, ref_title, url])
        if EXCLUDE_TITLE.search(anchor or "") and not STRONG_RE.search(anchor or ""):
            self.skipped.append({"url": url, "reason": "irrelevant anchor"})
            return
        if score(ctx) <= 0:
            self.skipped.append({"url": url, "reason": "not relevant"})
            return
        r = self.get(url, stream=True)
        if r is None:
            return
        data = b""
        for chunk in r.iter_content(1 << 16):
            data += chunk
            if len(data) > 80 * 1024 * 1024:
                self.failures.append({"url": url, "error": "file > 80 MB, skipped"})
                return
        if data[:15].lower().startswith((b"<!doctype", b"<html")) or b"<html" in data[:300].lower():
            self.failures.append({"url": url, "error": "got HTML instead of a document"})
            return
        self.docs_fetched += 1
        title = anchor.strip() or fname
        if title.lower() in ("تحميل", "download", "اضغط هنا", "هنا", "رابط", "الملف", "pdf"):
            title = f"{ref_title} - {fname}" if ref_title else fname
        ext = ext_of(url).lstrip(".")
        cat = categorize(anchor, ref_title, fname, url)
        name = f"{sanitize(title, 70)}__{sanitize(Path(fname).stem, 30)}.{ext}"
        self.save(cat, name, data, title, url, referrer, ext)

    # -- pages
    def extract_page(self, url: str, html: str) -> tuple[str, str, list[tuple[str, str]]]:
        soup = BeautifulSoup(html, "lxml")
        title = (soup.title.get_text(" ", strip=True) if soup.title else "") or url
        title = re.sub(r"\s*\|\s*جامعة الإمام محمد بن سعود الإسلامية\s*$", "", title).strip()
        links: list[tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            text = a.get_text(" ", strip=True)
            fname = unquote(href.split("?")[0].rsplit("/", 1)[-1])
            if ext_of(href) in DOC_EXT and (not text or text == fname or text in GENERIC_ANCHORS
                                            or len(text) < 4):
                row = a.find_parent(["tr", "li", "p"])
                if row is not None:
                    text = re.sub(r"\s+", " ", row.get_text(" ", strip=True)).replace(fname, "").strip()[:120] or text
            links.append((urljoin(url, href), text))
        host = urlsplit(url).hostname or ""
        body = ""
        if "__next_f" in html:  # Next.js main site
            payload = next_payload(html)
            # Content is streamed into hidden <div id="S:n"> blocks outside <main>, so read the body.
            main = BeautifulSoup(str(soup.body or soup), "lxml")
            for el in main.select("header, footer, nav, [role=navigation], [role=banner], [role=contentinfo]"):
                el.decompose()
            visible = cut_feedback(element_to_md(main))
            visible = re.sub(r"^.*?كيف تتحقق؟", "", visible, flags=re.S).strip()
            visible = re.sub(r"^\s*(\$\??|/\$)\s*$", "", visible, flags=re.M).strip()
            parts = [visible]
            faq = payload_faq(payload)
            if faq:
                parts.append("\n\n## الأسئلة والأجوبة\n\n" + "\n\n".join(f"**س: {q}**\n\nج: {a}" for q, a in faq))
            extra = []
            seen_txt = set(visible.split("\n"))
            for s_ in payload_strings(payload):
                t = html_fragment_to_text(s_)
                if t in self.boiler or t in seen_txt or any(t in a for _, a in faq) or any(t == q for q, _ in faq):
                    continue
                if t not in extra and t not in visible:
                    extra.append(t)
            if extra:
                parts.append("\n\n## محتوى إضافي من بيانات الصفحة\n\n" + "\n\n".join(extra))
            body = "\n".join(parts)
            for u, _ in payload_links(payload):
                links.append((urljoin(url, u), ""))
        else:  # SharePoint
            fields = soup.select(".ms-rtestate-field, #DeltaPlaceHolderMain, .page-content, article")
            chunks, seen_c = [], set()
            for f in fields:
                t = cut_feedback(element_to_md(f))
                if t and t not in seen_c and not any(t in c for c in chunks):
                    chunks = [c for c in chunks if c not in t]
                    chunks.append(t)
                    seen_c.add(t)
            body = "\n\n".join(chunks)
            if len(body) < 200:
                body = cut_feedback(element_to_md(soup.body or soup))
            body = re.sub(r"\{\{[^}]*\}\}", "", body)
        return title, body, links

    def handle_page(self, url: str, depth: int, referrer: str, anchor: str):
        if self.pages_fetched >= self.max_pages:
            return
        r = self.get(url)
        self.pages_fetched += 1
        if r is None:
            return
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype:
            if any(x in ctype for x in ("pdf", "officedocument", "msword", "excel", "powerpoint")):
                self.handle_doc(url, referrer, anchor, "")
            return
        r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8"
        html = r.text
        title, body, links = self.extract_page(r.url, html)
        print(f"[page {self.pages_fetched}/{self.max_pages} d{depth} q{len(self.queue)}] {title[:60]} <- {url}", flush=True)
        self.log_event("page", url=url, title=title, depth=depth, chars=len(body))

        # learn the unit site's menu once
        sp = urlsplit(r.url)
        if sp.hostname == "units.imamu.edu.sa":
            segs = [s for s in sp.path.split("/") if s]
            if len(segs) >= 2 and segs[0].lower() in ("deanships", "colleges", "institutes"):
                self.unit_menu(f"https://units.imamu.edu.sa/{segs[0]}/{segs[1]}", depth)

        # decide whether to save the page
        head = f"{title} {anchor} {unquote(url)}"
        sc_head = score(head)
        excluded = bool(EXCLUDE_TITLE.search(title)) and not STRONG_RE.search(title)
        if body and len(body) >= 250 and not excluded and (STRONG_RE.search(head) or sc_head >= 2):
            cat = categorize(title, anchor, unquote(url))
            self.save_md(cat, title, url, referrer, body)

        # follow links
        for href, text in links:
            u = norm_url(href)
            if not u:
                continue
            if ext_of(u) in DOC_EXT:
                if u not in self.seen:
                    self.seen.add(u)
                    self.handle_doc(u, url, text, title)
                continue
            prio = score(f"{text} {unquote(u)}") + (2 if sc_head > 0 else 0)
            if prio < 0:
                continue
            self.push(u, depth + 1, prio, url, text)

    def unit_menu(self, site: str, depth: int):
        if site.lower() in self.unit_sites_done:
            return
        self.unit_sites_done.add(site.lower())
        api = f"{site}/_layouts/15/NewUnits/Handlers/UnitHomeComponents.ashx?action=headerinfo"
        r = self.get(api, headers={"Accept": "application/json"})
        if r is None:
            return
        try:
            res = r.json().get("Result") or {}
        except ValueError:
            return
        n = 0
        for m in res.get("MainMenu") or []:
            items = [m] + (m.get("SubMenu") or [])
            for it in items:
                u, t = it.get("URL") or "", it.get("Title") or ""
                if not u:
                    continue
                u = urljoin(site + "/", u)
                if ext_of(u) in DOC_EXT:
                    nu = norm_url(u)
                    if nu and nu not in self.seen:
                        self.seen.add(nu)
                        self.handle_doc(nu, site, t, res.get("SiteTitle", ""))
                    continue
                self.push(u, depth + 1, score(f"{t} {u}") + 3, site, t)
                n += 1
        self.log_event("unit_menu", site=site, items=n)

    def learn_boilerplate(self):
        r = self.get(BASELINE_PAGE)
        if r is not None:
            r.encoding = "utf-8"
            for s_ in payload_strings(next_payload(r.text)):
                self.boiler.add(html_fragment_to_text(s_))

    # -- regulations platform
    def crawl_laws(self):
        print("== Regulations platform ==", flush=True)
        regs, page = [], 1
        while True:
            params = {"action": "advsearch", "accMode": "G", "modiMode": "G", "notiMode": "G",
                      "searchText": "", "benef": "-1", "accNumber": "", "cId": "-1", "statusId": "-1",
                      "fromAcc": "", "toAcc": "", "fromNoti": "", "toNoti": "", "fromModi": "",
                      "toModi": "", "pageNumber": page, "pageSize": 12}
            r = self.get(LAWS_HANDLER, params=params, headers={"Accept": "application/json"})
            if r is None:
                break
            try:
                data = r.json()
            except ValueError:
                self.failures.append({"url": r.url, "error": "laws list not JSON"})
                break
            if not data:
                break
            regs.extend(data)
            total = data[0].get("TotalRows") or 0
            if page * 12 >= total:
                break
            page += 1
        print(f"   {len(regs)} regulations listed", flush=True)
        live = [g for g in regs if g.get("StatusId") == 0]
        self.laws_stats = {"listed": len(regs), "in_force": len(live), "saved": 0, "skipped_not_student": []}
        for g in live:
            rid = g["Id"]
            r = self.get(LAWS_HANDLER, params={"action": "getregulationbyid", "itemid": rid},
                         headers={"Accept": "application/json"})
            if r is None:
                continue
            try:
                d = r.json()
                d = d[0] if isinstance(d, list) and d else None
                if not isinstance(d, dict):
                    raise ValueError("unexpected response")
            except (ValueError, IndexError, KeyError, TypeError):
                self.failures.append({"url": r.url, "error": "regulation not JSON"})
                continue
            name = d.get("Name") or g.get("Name") or f"regulation {rid}"
            benef = d.get("Beneficiaries") or ""
            cls = d.get("ClassificationTxt") or ""
            student = ("الطلاب" in benef or "أكاديمية" in cls
                       or re.search(r"طلاب|طالب|الدراس|القبول|التسجيل|الاختبار|المكافآت|التأديب|السكن|الخطط|"
                                    r"المقررات|الدبلوم|الماجستير|الدكتوراه|المنح", name))
            if self.focus and not FOCUS_LAWS.search(name):
                student = False
            if not student:
                self.laws_stats["skipped_not_student"].append(name)
                continue
            body = drop_repeated_tail(html_fragment_to_text(d.get("FullText") or ""))
            if len(body) < 100:
                r2 = self.get(LAWS_HANDLER, params={"action": "getstatutebyregulationid", "itemid": rid},
                              headers={"Accept": "application/json"})
                try:
                    sts = r2.json() if r2 is not None else []
                except ValueError:
                    sts = []
                body = "\n\n".join(f"## {s.get('Name', '')}\n\n{html_fragment_to_text(s.get('Content') or '')}"
                                   for s in sts)
            meta = (f"- الحالة: {d.get('StatusTxt', '')}\n- التصنيف: {cls}\n- المستفيدون: {benef}\n"
                    f"- الجهة: {d.get('Department') or ''}\n- رقم قرار الاعتماد: {d.get('AccreditationNumber') or ''}\n"
                    f"- تاريخ الاعتماد: {d.get('AccreditationDateString') or ''} هـ\n"
                    f"- تاريخ آخر تعديل: {d.get('ModificationDateString') or ''} هـ\n\n")
            cat = categorize(name)
            if cat not in ("graduate_studies", "fees_and_rewards", "student_affairs", "admission_registration",
                           "forms", "academic_calendar"):
                cat = "regulations"
            if cat == "student_affairs" and not re.search(r"تأديب|حقوق|سكن|نشاط|شؤون", name):
                cat = "regulations"
            url = LAWS_DETAILS.format(rid=rid)
            self.save_md(cat, name, url, "https://imamu.edu.sa/laws/", meta + body)
            self.laws_stats["saved"] += 1

    # -- main loop
    def run(self, skip_laws: bool):
        self.robots_for("imamu.edu.sa")
        self.learn_boilerplate()
        if not skip_laws:
            self.laws_stats = {"listed": 0, "in_force": 0, "saved": 0, "skipped_not_student": []}
            try:
                self.crawl_laws()
            except Exception as e:  # never lose the website crawl because of the laws step
                self.failures.append({"url": LAWS_HANDLER, "error": f"laws step: {type(e).__name__}: {e}"[:300]})
        else:
            self.laws_stats = {"listed": 0, "in_force": 0, "saved": 0, "skipped_not_student": []}
        print("== Website crawl ==", flush=True)
        for s_ in (FOCUS_SEEDS if self.focus else SEEDS):
            self.push(s_, 0, 100)
        for site in (FOCUS_UNIT_SITES if self.focus else UNIT_SITES):
            self.unit_menu(site, 0)
        while self.queue and self.pages_fetched < self.max_pages:
            _, depth, _, url, ref, anchor = heapq.heappop(self.queue)
            try:
                self.handle_page(url, depth, ref, anchor)
            except Exception as e:  # keep crawling on parser surprises
                self.failures.append({"url": url, "error": f"{type(e).__name__}: {e}"[:300]})
        self.left_in_queue = len(self.queue)

    # -- reports
    def write_reports(self):
        with open(self.out / "INDEX.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["category", "file_name", "title", "source_url", "referring_page",
                                              "file_type", "size_bytes", "sha256", "downloaded_at"])
            w.writeheader()
            for row in sorted(self.index, key=lambda r: (r["category"], r["file_name"])):
                w.writerow(row)
        scanned = []
        if PdfReader is not None:
            for row in self.index:
                if row["file_type"] != "pdf":
                    continue
                try:
                    rd = PdfReader(io.BytesIO((self.out / row["file_name"]).read_bytes()))
                    pages = rd.pages[:5]
                    chars = sum(len((p.extract_text() or "").strip()) for p in pages)
                    if chars < 40 * max(1, len(pages)):
                        scanned.append((row["file_name"], len(rd.pages)))
                except Exception as e:
                    scanned.append((row["file_name"], f"unreadable: {type(e).__name__}"))
        (self.out / "_failures.json").write_text(json.dumps(
            {"failures": self.failures, "skipped": self.skipped}, ensure_ascii=False, indent=1), encoding="utf-8")
        counts: dict[str, list[int]] = {}
        for row in self.index:
            c = counts.setdefault(row["category"], [0, 0, 0])
            c[0] += 1
            c[1 if row["file_type"] == "md" else 2] += 1
        lines = ["# Raw university documents — crawl summary", "",
                 f"Crawled: {now_iso()} from https://imamu.edu.sa (public pages only).", "",
                 f"- Pages fetched: {self.pages_fetched} (cap {self.max_pages}), documents downloaded: {self.docs_fetched}",
                 f"- URLs still in queue when the crawl stopped: {getattr(self, 'left_in_queue', 0)}",
                 f"- Files saved (after SHA-256 dedup): {len(self.index)}", "",
                 "## Files per category", "", "| Category | Total | Pages (.md) | Documents |", "|---|---|---|---|"]
        for c in sorted(counts):
            lines.append(f"| {c} | {counts[c][0]} | {counts[c][1]} | {counts[c][2]} |")
        ls = self.laws_stats
        lines += ["", "## Regulations platform (منصة نظام)", "",
                  f"- Regulations listed: {ls['listed']}, in force: {ls['in_force']}, saved as text: {ls['saved']}",
                  "- Regulation PDF files on the platform need a login, so they were **not** downloaded; the full"
                  " text that the public details page shows was saved instead (one .md per regulation).",
                  f"- Skipped as not student-related ({len(ls['skipped_not_student'])}): "
                  + "; ".join(ls["skipped_not_student"][:60]), "",
                  "## Scanned PDFs (no text layer — run scripts/ocr_pdf.py)", ""]
        lines += [f"- {n} ({p} pages)" for n, p in scanned] or ["- none detected"]
        lines += ["", "## Failures", "", f"{len(self.failures)} failed URLs (details in _failures.json)", ""]
        lines += [f"- {f['url']} — {f['error']}" for f in self.failures[:40]]
        reasons: dict[str, int] = {}
        for s_ in self.skipped:
            reasons[s_["reason"].split(" http")[0]] = reasons.get(s_["reason"].split(" http")[0], 0) + 1
        lines += ["", "## Skipped (not fetched)", ""] + [f"- {k}: {v}" for k, v in sorted(reasons.items())]
        (self.out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return scanned


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="raw_university_docs")
    ap.add_argument("--max-pages", type=int, default=3000)
    ap.add_argument("--max-depth", type=int, default=4)
    ap.add_argument("--max-docs", type=int, default=1500)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--skip-laws", action="store_true")
    ap.add_argument("--focus", action="store_true",
                    help="only CCIS, Admission & Registration, academic calendar and core regulations")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    c = Crawler(out, a.max_pages, a.max_depth, max(1.0, a.delay), a.max_docs, a.focus)
    try:
        c.run(a.skip_laws)
    except KeyboardInterrupt:
        print("interrupted — writing reports", flush=True)
    c.write_reports()
    print(f"done: {len(c.index)} files saved, {len(c.failures)} failures", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
