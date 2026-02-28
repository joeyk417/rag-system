from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    tenant_id: str = Field(pattern=r"^[a-z0-9_]+$")  # slug, e.g. "elastomers_au"
    name: str
    config: dict = {}


class TenantPatch(BaseModel):
    config: dict | None = None
    is_active: bool | None = None


class TenantResponse(BaseModel):
    id: UUID
    tenant_id: str
    name: str
    schema_name: str
    s3_prefix: str
    config: dict
    is_active: bool
    created_at: datetime


class TenantCreateResponse(TenantResponse):
    api_key: str  # plaintext — shown once, not stored
