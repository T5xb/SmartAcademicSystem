import os
import re
from typing import List, Optional

from llama_index.core import QueryBundle
from llama_index.core.indices.base import BaseIndex
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore
from llama_index.core.tools.query_engine import QueryEngineTool

# Graduate-studies documents (master's, PhD, theses). Their rules differ from
# the bachelor's ones (e.g. an academic warning below 3.75, not 2.00), and the
# chatbot's users are undergraduates, so they are used only when asked about.
_GRAD_DOC_RE = re.compile(r"الدراسات_العليا|ماجستير|دكتوراه|الرسائل_العلمية")
_GRAD_QUESTION_RE = re.compile(
    r"عليا|ماجستير|ماستر|دكتوراه|دكتوراة|رسال[ةه]\s*علمي|الرسائل\s*العلمي|master|phd", re.IGNORECASE
)
# Extra chunks fetched so the top_k is still full after the filter.
_SCOPE_MARGIN = 6


class ScopeFilter(BaseNodePostprocessor):
    """Drops graduate-studies chunks unless the question is about graduate studies."""

    top_k: int = 8

    def _postprocess_nodes(
        self, nodes: List[NodeWithScore], query_bundle: Optional[QueryBundle] = None
    ) -> List[NodeWithScore]:
        question = query_bundle.query_str if query_bundle else ""
        if not _GRAD_QUESTION_RE.search(question):
            kept = [
                n for n in nodes
                if not _GRAD_DOC_RE.search(os.path.basename(n.node.metadata.get("file_name", "")))
            ]
            nodes = kept or nodes
        return nodes[: self.top_k]


def get_query_engine_tool(index: BaseIndex) -> QueryEngineTool:
    """The index as a query tool. TOP_K (src/.env) sets how many chunks reach the model."""
    top_k = int(os.getenv("TOP_K", 0)) or 2
    return QueryEngineTool.from_defaults(
        query_engine=index.as_query_engine(
            similarity_top_k=top_k + _SCOPE_MARGIN,
            node_postprocessors=[ScopeFilter(top_k=top_k)],
        ),
        name="query_index",
        description="Use this tool to retrieve information from a knowledge base. Provide a specific query and can call the tool multiple times if necessary.",
    )
