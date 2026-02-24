from __future__ import annotations

# TODO: implement in Task 3
# Pydantic v2 schemas:
#
# class IngestResponse(BaseModel):
#     job_id: UUID
#     status: Literal["pending", "processing", "completed", "failed"]
#     document_id: UUID | None = None
#     message: str
#
# class JobStatusResponse(BaseModel):
#     job_id: UUID
#     status: Literal["pending", "processing", "completed", "failed"]
#     document_id: UUID | None = None
#     error: str | None = None
#     created_at: datetime
#     updated_at: datetime
