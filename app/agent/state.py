from __future__ import annotations

from typing_extensions import TypedDict

from app.schemas.chat import Source, TokenUsage
from app.schemas.retrieval import RetrievedChunk


class AgentState(TypedDict):
    query: str                            # original user query
    rewritten_query: str                  # populated by rewrite_node when grade fails
    retrieved_docs: list[RetrievedChunk]  # output of retrieve_node (vector search)
    web_results: str                      # Tavily fallback results as formatted text
    is_relevant: bool                     # output of grade_node
    answer: str                           # final generated answer
    sources: list[Source]                 # citations (populated on vector path only)
    usage: TokenUsage | None              # LLM token usage from generate_node
