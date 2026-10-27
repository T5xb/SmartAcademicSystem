from dotenv import load_dotenv

from llama_index.core.tools.query_engine import QueryEngineTool

from src.index import get_index
from src.query import get_query_engine_tool
from src.citation import enable_citation, format_citations
from src.settings import init_settings
from src.quick_answers import quick_reply
from src.student_style import expand_query, small_talk_reply, with_greeting


class DirectQueryWorkflow:
  

    def __init__(self, query_engine_tool: QueryEngineTool):
        self._query_engine_tool = query_engine_tool

    async def run(self, user_msg: str) -> str:
        # A bare greeting or thanks has nothing to look up.
        canned = small_talk_reply(user_msg)
        if canned:
            return canned
        # A whole plan/calendar file, or one calendar date: exact lookups.
        quick = quick_reply(user_msg)
        if quick:
            return with_greeting(user_msg, quick)
        # Dialect and short forms are mapped to the documents' own terms.
        output = await self._query_engine_tool.acall(input=expand_query(user_msg))
        source_nodes = getattr(output.raw_output, "source_nodes", None) or []
        return with_greeting(user_msg, format_citations(output.content, source_nodes))


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
