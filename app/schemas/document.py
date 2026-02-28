from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    doc_number: str | None
    doc_type: str | None
    revision: str | None
    title: str | None
    classification: str | None
    page_count: int | None
    status: str
    created_at: datetime
