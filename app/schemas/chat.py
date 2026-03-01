from __future__ import annotations

from pydantic import BaseModel, Field


class Source(BaseModel):
    doc_number: str | None
    title: str | None
    page_number: int
    s3_key: str
    score: float | None = None  # relevance score 0–1 (1 = perfect match)


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    query: str
    usage: TokenUsage | None = None
