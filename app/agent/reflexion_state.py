from __future__ import annotations

from pydantic import BaseModel
from typing_extensions import TypedDict

from app.schemas.chat import Source, TokenUsage
from app.schemas.retrieval import RetrievedChunk


class ReflexionState(TypedDict):
    query: str
    answer: str
    reflection: str               # what is still missing / what was superfluous
    search_queries: list[str]     # sub-queries for next retrieval round
    retrieved_docs: list[RetrievedChunk]
    sources: list[Source]
    is_complete: bool
    iteration_count: int
    usage: TokenUsage | None


class ReflexionAnswer(BaseModel):
    answer: str              # 250-300 words, markdown
    reflection: str          # what information is still missing
    search_queries: list[str]  # 1-3 specific sub-queries for next iteration
    is_complete: bool        # True when answer fully addresses the question
