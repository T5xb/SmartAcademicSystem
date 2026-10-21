

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

_ORDINAL = (
    r"(?:ال)?(?:أولى|اولى|ثانية|ثالثة|رابعة|خامسة|سادسة|سابعة|ثامنة|تاسعة|"
    r"عاشرة|حادية)"
)
_TENS = (
    r"(?:\s+(?:عشرة|عشر|و?ال(?:عشرون|عشرين|ثلاثون|ثلاثين|أربعون|أربعين|"
    r"خمسون|خمسين|ستون|ستين|سبعون|سبعين)))?"
)
ARTICLE_RE = re.compile(rf"المادة\s+(?:{_ORDINAL}{_TENS}|\d+)")



NO_ANSWER_SENTINEL = "لا_توجد_إجابة_في_الوثائق"

ADVISING_EMAIL = os.getenv("ADVISING_EMAIL", "cs.acadv@imamu.edu.sa")

NO_ANSWER_MESSAGE = (
    "لم أجد إجابة لسؤالك في الوثائق الرسمية المتاحة لي.\n\n"
    "الرجاء التواصل مع الإرشاد الأكاديمي لخدمتك على البريد الإلكتروني:\n"
    f"{ADVISING_EMAIL}"
)



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
    
    query_engine = query_engine_tool.query_engine
    if not isinstance(query_engine, RetrieverQueryEngine):
        raise ValueError(
            "Citation feature requires a RetrieverQueryEngine. Your tool's query engine is a "
            f"{type(query_engine)}."
        )
    
    query_engine._response_synthesizer = CitationSynthesizer()
    query_engine._node_postprocessors += [NodeCitationProcessor()]
    query_engine_tool._query_engine = query_engine

   
    query_engine_tool.metadata.description += "\nThe output will include citations with the format [citation:id] for each chunk of information in the knowledge base."
    return query_engine_tool



CITATION_TAG_RE = re.compile(r"[\[(]citation:\s*([^\])]*?)\s*[\])]")


def format_citations(answer: str, source_nodes: List[NodeWithScore]) -> str:
   
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
