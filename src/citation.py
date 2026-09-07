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

# Matches an Arabic legal "Article" marker, e.g. "المادة الأولى" or
# "المادة 12", so a chunk can be tagged with which article it's from.
ARTICLE_RE = re.compile(r"المادة\s+(?:ال)?\S+")


# Prompts for the citation-aware synthesizer, in Arabic (the users are
# Arabic speakers, and writing the instructions themselves in Arabic keeps
# the whole prompt in one language, which this small local model follows
# more reliably than switching between English instructions and an Arabic
# answer). Kept short and concrete: this model degrades (repeats itself,
# echoes instructions, mixes in other languages) on long, English, few-shot
# style prompts -- an earlier version with a literal example block caused
# it to copy the example's fake citation IDs verbatim instead of using
# real ones.
#
# There are two templates because the underlying synthesizer (see
# CitationSynthesizer below) packs as many retrieved chunks as fit into
# one call using CITATION_QA_PROMPT, then -- only if chunks are left over --
# folds each remaining chunk in with CITATION_REFINE_PROMPT. Both must
# carry the same citation/Arabic/"don't guess" rules, or the refine step
# (which otherwise falls back to a generic English default with none of
# those rules) undoes them.
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
- إذا لم يحتوِ السياق على إجابة للسؤال، قل بجملة واحدة إن المعلومة غير متوفرة في الوثائق المتاحة، ولا تخترع إجابة.
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


# Add this prompt to your agent system prompt
CITATION_SYSTEM_PROMPT = (
    "\nAnswer the user question using the response from the query tool. "
    "It's important to respect the citation information in the response. "
    "Don't mix up the citation_id, keep them at the correct fact."
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


# Matches [citation:id] and, since the model sometimes writes it with
# parens instead of the requested square brackets, (citation: id) too.
# Captures everything up to the closing bracket/paren, not just a single
# "word" -- a weak model sometimes writes a multi-word phrase (its own
# wording, not the real id) inside the tag instead of the real node id.
# We still want to catch and strip those, not leave them visible.
CITATION_TAG_RE = re.compile(r"[\[(]citation:\s*([^\])]*?)\s*[\])]")


def format_citations(answer: str, source_nodes: List[NodeWithScore]) -> str:
    """
    Replace the model's [citation:<node_id>] tags with numbered footnote
    markers ([1], [2], ...), and append a "المصادر" (Sources) section built
    from the *actual* retrieved nodes' metadata -- file name, page number
    (when known), and article marker (when detected).

    This is deliberately not left to the LLM: asking a small local model to
    transcribe an exact file name and page number into free text is asking
    it to hallucinate. Here the model only has to copy an opaque id it was
    given verbatim, which is a much easier task, and our own code resolves
    that id to the real source. A tag that doesn't match any retrieved node
    (e.g. a stray or fabricated id) is silently dropped rather than shown.
    """
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
