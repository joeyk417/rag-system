from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class IngestResponse(BaseModel):
    job_id: UUID | None  # None when file was already ingested (fast dedup path)
    status: Literal["pending", "completed"]
    document_id: UUID | None = None
    message: str


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: Literal["pending", "processing", "completed", "failed"]
    document_id: UUID | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
