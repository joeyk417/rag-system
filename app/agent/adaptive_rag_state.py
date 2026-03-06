from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from typing_extensions import TypedDict

from app.schemas.chat import Source, TokenUsage
from app.schemas.retrieval import RetrievedChunk


class AdaptiveRAGState(TypedDict):
    query: str
    datasource: str                    # "retrieve" | "web_search" | "sql_agent"
    rewritten_queries: list[str]       # accumulates across transform_query calls
    retrieved_docs: list[RetrievedChunk]
    answer: str
    sources: list[Source]
    usage: TokenUsage | None
    iteration_count: int               # safety guard for Self-RAG inner loop


class RouterQuery(BaseModel):
    datasource: Literal["retrieve", "web_search", "sql_agent"]
    reasoning: str = ""
