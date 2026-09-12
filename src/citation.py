"""
Source-attributed answers: the Arabic prompts, and turning the model's
citation tags into a real "المصادر" list.

The guiding rule (ARCHITECTURE.md §4.5-4.6): the LLM only ever emits
opaque markers, and this module substitutes the real text. It never
transcribes a filename, page number or email itself.
"""

import os
import re
from typing import Any, List, Optional

from llama_index.core import QueryBundle
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.prompts import PromptTemplate
from llama_index.core.query_engine.retriever_query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import CompactAndRefine
from llama_index.core.schema import NodeWithScore
from llama_index.core.tools.query_engine import QueryEngineTool

# Tags a chunk with the article it comes from, e.g. "المادة الأولى",
# "المادة الثانية والعشرون", "المادة 12".
#
# Matches a closed set of ordinals plus an optional "tens" tail rather
# than "المادة" + any one token: that looser version collapsed articles
# 2, 12 and 22 into the same label (so citations named the wrong article)
# and also matched OCR noise like "المادة )". The tens tail allows the
# missing-waw spelling the OCR produces ("المادة الخامسة العشرون").
_ORDINAL = (
    r"(?:ال)?(?:أولى|اولى|ثانية|ثالثة|رابعة|خامسة|سادسة|سابعة|ثامنة|تاسعة|"
    r"عاشرة|حادية)"
)
_TENS = (
    r"(?:\s+(?:عشرة|عشر|و?ال(?:عشرون|عشرين|ثلاثون|ثلاثين|أربعون|أربعين|"
    r"خمسون|خمسين|ستون|ستين|سبعون|سبعين)))?"
)
ARTICLE_RE = re.compile(rf"المادة\s+(?:{_ORDINAL}{_TENS}|\d+)")


# When the documents don't answer the question, hand off to a human
# advisor instead of a vague "not found". The model only emits the
# sentinel; the message and email below are substituted by our code, since
# an LLM transcribing an email address risks mangling it and a wrong
# advising address is worse than none.
NO_ANSWER_SENTINEL = "لا_توجد_إجابة_في_الوثائق"

# Overridable so a different department/advisor can be pointed to without
# touching code.
ADVISING_EMAIL = os.getenv("ADVISING_EMAIL", "cs.acadv@imamu.edu.sa")

NO_ANSWER_MESSAGE = (
    "لم أجد إجابة لسؤالك في الوثائق الرسمية المتاحة لي.\n\n"
    "الرجاء التواصل مع الإرشاد الأكاديمي لخدمتك على البريد الإلكتروني:\n"
    f"{ADVISING_EMAIL}"
)


# Prompts are written in Arabic throughout: keeping instructions and
# answer in one language is followed more reliably than mixing English
# instructions with an Arabic answer, and they are kept short because weak
# models start echoing long prompts back (an early version with a worked
# example made the model copy that example's fake citation ids).
#
# Two templates: the synthesizer packs as many chunks as fit into one call
# with the QA prompt, then folds any leftovers in with the REFINE prompt.
# Both must carry the same rules, or the refine step (whose default is a
# generic English prompt) undoes them.
CITATION_QA_PROMPT = """السياق التالي مقتطفات من وثائق، كل مقطع منه يبدأ برقم تعريف (citation_id).

السياق:
------------------
{context_str}
------------------

السؤال: {query_str}

التعليمات:
- أجب بالعربية الفصحى فقط، بإجابة واحدة مباشرة وواضحة.
- اعتمد فقط على معلومات السياق أعلاه، ولا تستخدم أي معرفة خارجية.
- بعد كل معلومة تنقلها من السياق، أضف رمز الاقتباس الحقيقي المرتبط بها بهذا الشكل: [citation:المعرف].
- إذا لم يحتوِ السياق على إجابة للسؤال، فاكتب هذه الكلمة وحدها بلا أي نص آخر: لا_توجد_إجابة_في_الوثائق — ولا تخترع إجابة ولا تعتذر ولا تضف شيئًا بعدها.
- لا تكتب أمثلة توضيحية، ولا تكرر السؤال، ولا تشرح طريقة عملك.

الإجابة:
"""

CITATION_REFINE_PROMPT = """أنت تُكمل إجابة عربية عن سؤال بالاعتماد على مقطع سياق إضافي.

السؤال: {query_str}

الإجابة الحالية: {existing_answer}

مقطع سياق إضافي (قد يبدأ بجزء منه برقم تعريف citation_id):
------------------
{context_msg}
------------------

التعليمات:
- إذا أضاف هذا المقطع معلومة مفيدة غير موجودة بالإجابة الحالية، وسّع الإجابة لتشملها مع رمز اقتباسها [citation:المعرف].
- إذا كانت الإجابة الحالية هي لا_توجد_إجابة_في_الوثائق وكان هذا المقطع يحتوي الإجابة، فاكتب الإجابة الصحيحة مع رمز اقتباسها واحذف تلك الكلمة.
- إذا كانت الإجابة الحالية هي لا_توجد_إجابة_في_الوثائق وهذا المقطع أيضًا لا يحتوي الإجابة، فأعد كتابة لا_توجد_إجابة_في_الوثائق وحدها بلا أي نص آخر.
- إذا لم يكن مفيدًا، أعد الإجابة الحالية كما هي دون أي تغيير.
- أجب بالعربية الفصحى فقط، بإجابة واحدة مباشرة، بدون شرح طريقة عملك.

الإجابة النهائية:
"""


class NodeCitationProcessor(BaseNodePostprocessor):
    """
    Add a `citation_id` field to each node's metadata (copied from the node
    id), and, if the chunk's text contains an Arabic "Article" marker (e.g.
    "المادة الأولى"), an `article` field -- both used later to build a
    human-readable source list (see format_citations below).
    """

    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        for node_score in nodes:
            node = node_score.node
            node.metadata["citation_id"] = node.node_id
            match = ARTICLE_RE.search(node.get_content())
            if match:
                node.metadata["article"] = match.group(0)
        return nodes


class CitationSynthesizer(CompactAndRefine):
    """
    Overload the CompactAndRefine synthesizer to:
    1. Update prepare node metadata for citation id
    2. Use citation-aware, Arabic prompts for both synthesis steps

    Note: this used to subclass `Accumulate`, which calls the LLM once
    per retrieved chunk (and concatenates the answers). That's very slow
    on CPU-only local models. `CompactAndRefine` packs all chunks into as
    few LLM calls as possible (ideally just one), which keeps the same
    citation behavior but is much faster.
    """

    def __init__(self, **kwargs: Any) -> None:
        text_qa_template = kwargs.pop("text_qa_template", None)
        if text_qa_template is None:
            text_qa_template = PromptTemplate(template=CITATION_QA_PROMPT)
        refine_template = kwargs.pop("refine_template", None)
        if refine_template is None:
            refine_template = PromptTemplate(template=CITATION_REFINE_PROMPT)
        super().__init__(
            text_qa_template=text_qa_template,
            refine_template=refine_template,
            **kwargs,
        )


def enable_citation(query_engine_tool: QueryEngineTool) -> QueryEngineTool:
    """
    Enable citation for a query engine tool by using CitationSynthesizer and NodePostprocessor.
    Note: This function will override the response synthesizer of your query engine.
    """
    query_engine = query_engine_tool.query_engine
    if not isinstance(query_engine, RetrieverQueryEngine):
        raise ValueError(
            "Citation feature requires a RetrieverQueryEngine. Your tool's query engine is a "
            f"{type(query_engine)}."
        )
    # Update the response synthesizer and node postprocessors
    query_engine._response_synthesizer = CitationSynthesizer()
    query_engine._node_postprocessors += [NodeCitationProcessor()]
    query_engine_tool._query_engine = query_engine

    # Update tool metadata
    query_engine_tool.metadata.description += "\nThe output will include citations with the format [citation:id] for each chunk of information in the knowledge base."
    return query_engine_tool


# Matches [citation:id], and (citation: id) too since the model sometimes
# uses parens. Captures up to the closing bracket rather than one word, so
# that a model writing its own phrase instead of the real id still gets
# stripped rather than shown to the user.
CITATION_TAG_RE = re.compile(r"[\[(]citation:\s*([^\])]*?)\s*[\])]")


def format_citations(answer: str, source_nodes: List[NodeWithScore]) -> str:
    """
    Turns [citation:<node_id>] tags into footnote markers ([1], [2], ...)
    and appends a "المصادر" section built from the *actual* retrieved
    nodes' metadata: file name, page number and article when known.

    Resolving ids here rather than asking the LLM for filenames is the
    whole point — the model copies back an opaque id it was just given,
    which it can do reliably. Tags matching no retrieved node (stray or
    fabricated) are dropped rather than shown.

    The "no answer" sentinel replaces the whole answer with the advisor
    handoff, with no sources section since nothing was cited.
    """
    if NO_ANSWER_SENTINEL in answer:
        return NO_ANSWER_MESSAGE

    nodes_by_id = {n.node.node_id: n.node for n in source_nodes}
    order: List[str] = []
    numbers: dict[str, int] = {}

    def _replace(m: "re.Match[str]") -> str:
        node_id = m.group(1)
        if node_id not in nodes_by_id:
            return ""
        if node_id not in numbers:
            numbers[node_id] = len(order) + 1
            order.append(node_id)
        return f"[{numbers[node_id]}]"

    body = CITATION_TAG_RE.sub(_replace, answer).strip()
    if not order:
        return body

    lines = [body, "", "المصادر:"]
    for node_id in order:
        meta = nodes_by_id[node_id].metadata
        file_name = os.path.basename(meta.get("file_name", "غير معروف"))
        parts = [file_name]
        if meta.get("page_label"):
            parts.append(f"صفحة {meta['page_label']}")
        if meta.get("article"):
            parts.append(meta["article"])
        lines.append(f"[{numbers[node_id]}] " + " — ".join(parts))

    return "\n".join(lines)
