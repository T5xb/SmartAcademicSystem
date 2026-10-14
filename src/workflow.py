from dotenv import load_dotenv

from llama_index.core.tools.query_engine import QueryEngineTool

from src.index import get_index
from src.query import get_query_engine_tool
from src.citation import enable_citation, format_citations
from src.settings import init_settings


class DirectQueryWorkflow:
  

    def __init__(self, query_engine_tool: QueryEngineTool):
        self._query_engine_tool = query_engine_tool

    async def run(self, user_msg: str) -> str:
        output = await self._query_engine_tool.acall(input=user_msg)
        source_nodes = getattr(output.raw_output, "source_nodes", None) or []
        return format_citations(output.content, source_nodes)


def create_workflow() -> DirectQueryWorkflow:
    load_dotenv()
    init_settings()
    index = get_index()
    if index is None:
        raise RuntimeError(
            "Index not found! Please run `uv run generate` to index the data first."
        )
    # Create a query tool with citations enabled
    query_tool = enable_citation(get_query_engine_tool(index=index))

    return DirectQueryWorkflow(query_tool)
