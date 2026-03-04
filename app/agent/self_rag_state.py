from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from typing_extensions import TypedDict

from app.schemas.chat import Source, TokenUsage
from app.schemas.retrieval import RetrievedChunk


class SelfRAGState(TypedDict):
    query: str
    rewritten_queries: list[str]      # accumulates across transform_query calls
    retrieved_docs: list[RetrievedChunk]
    answer: str
    sources: list[Source]
    usage: TokenUsage | None
    iteration_count: int              # safety guard: caps hallucination retry loop


# ---------------------------------------------------------------------------
# Grading schemas (binary yes/no output, parsed from JSON responses)
# ---------------------------------------------------------------------------


class GradeDocuments(BaseModel):
    binary_score: Literal["yes", "no"]   # "yes" = document relevant to query


class GradeHallucinations(BaseModel):
    binary_score: Literal["yes", "no"]   # "yes" = answer grounded in retrieved facts


class GradeAnswer(BaseModel):
    binary_score: Literal["yes", "no"]   # "yes" = answer addresses the query


class SearchQueries(BaseModel):
    queries: list[str]   # 1-3 specific sub-queries; must differ from previous ones
