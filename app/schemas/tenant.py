from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.config import settings


class TenantCreate(BaseModel):
    tenant_id: str = Field(pattern=r"^[a-z0-9_]+$")  # slug, e.g. "elastomers_au"
    name: str
    config: dict = {}
    token_quota: int = Field(default_factory=lambda: settings.token_quota_starter, gt=0)


class TenantPatch(BaseModel):
    config: dict | None = None
    is_active: bool | None = None
    token_quota: int | None = Field(default=None, gt=0)


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


class TenantUsageResponse(BaseModel):
    tenant_id: str
    period_month: str  # ISO date string e.g. "2026-03-01"
    tokens_used: int
    input_tokens: int
    output_tokens: int
    token_quota: int
    percent_used: float
    estimated_cost_usd: float
    tier: str
