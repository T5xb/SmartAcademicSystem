import os

from llama_index.core.indices.base import BaseIndex
from llama_index.core.tools.query_engine import QueryEngineTool


def get_query_engine_tool(index: BaseIndex) -> QueryEngineTool:
    """The index as a query tool. TOP_K (src/.env) sets how many chunks are retrieved."""
    kwargs = {}
    top_k = int(os.getenv("TOP_K", 0))
    if top_k != 0:
        kwargs["similarity_top_k"] = top_k
    return QueryEngineTool.from_defaults(
        query_engine=index.as_query_engine(**kwargs),
        name="query_index",
        description="Use this tool to retrieve information from a knowledge base. Provide a specific query and can call the tool multiple times if necessary.",
    )
