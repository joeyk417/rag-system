from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    doc_number: str | None
    doc_type: str | None
    title: str | None
    classification: str | None
    s3_key: str
    page_number: int
    heading: str | None
    content: str
    similarity_score: float  # cosine distance from pgvector (<=> operator)
