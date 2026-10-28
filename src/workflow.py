from dotenv import load_dotenv

from llama_index.core.tools.query_engine import QueryEngineTool

from src.index import get_index
from src.query import get_query_engine_tool
from src.citation import NO_ANSWER_SENTINEL, enable_citation, format_citations
from src.clarify import TICKET_MARK, is_vague, pending_question, unanswered_reply
from src.tickets import build_ticket
from src.settings import init_settings
from src.quick_answers import quick_reply
from src.student_style import expand_query, small_talk_reply, with_greeting


class DirectQueryWorkflow:

    def __init__(self, query_engine_tool: QueryEngineTool):
        self._query_engine_tool = query_engine_tool

    async def run(self, user_msg: str, history: list | None = None) -> str:
        reply, _ = await self.respond(user_msg, history)
        return reply

    async def respond(
        self, user_msg: str, history: list | None = None
    ) -> tuple[str, dict | None]:
        """
        The reply, and a ticket draft when the reply suggests opening a
        ticket with academic advising (else None). `history` is the
        conversation so far as [{role: "user"|"bot", text}], oldest first.
        """
        # A bare greeting or thanks has nothing to look up.
        canned = small_talk_reply(user_msg)
        if canned:
            return canned, None
        # A whole plan/calendar file, or one calendar date: exact lookups.
        quick = quick_reply(user_msg)
        if quick:
            return with_greeting(user_msg, quick), None

        # After a clarifying question, the student's answer completes the
        # earlier message, so both are searched together.
        question = pending_question(history, user_msg)
        if is_vague(question):
            return self._unanswered(user_msg, question, history)

        # Dialect and short forms are mapped to the documents' own terms.
        output = await self._query_engine_tool.acall(input=expand_query(question))
        if NO_ANSWER_SENTINEL in output.content:
            return self._unanswered(user_msg, question, history)
        source_nodes = getattr(output.raw_output, "source_nodes", None) or []
        return with_greeting(user_msg, format_citations(output.content, source_nodes)), None

    @staticmethod
    def _unanswered(user_msg, question, history) -> tuple[str, dict | None]:
        reply = unanswered_reply(question, history)
        ticket = None
        if TICKET_MARK in reply:
            transcript = list(history or []) + [{"role": "user", "text": user_msg}]
            ticket = build_ticket(question, transcript)
        return with_greeting(user_msg, reply), ticket


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
