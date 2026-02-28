from __future__ import annotations

import hashlib
import logging
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant
from app.db.schema_utils import create_tenant_schema
from app.db.session import AsyncSessionLocal
from app.dependencies import get_admin, get_db
from app.schemas.tenant import TenantCreate, TenantCreateResponse, TenantPatch, TenantResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def _tenant_to_response(tenant: Tenant) -> TenantResponse:
    return TenantResponse(
        id=tenant.id,
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        schema_name=tenant.schema_name,
        s3_prefix=tenant.s3_prefix,
        config=tenant.config,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
    )


@router.post("/tenants", response_model=TenantCreateResponse, status_code=201)
async def create_tenant(
    body: TenantCreate,
    _: None = Depends(get_admin),
    session: AsyncSession = Depends(get_db),
) -> TenantCreateResponse:
    """Create a new tenant, provision its PostgreSQL schema, and return a one-time API key."""
    # Check for duplicate tenant_id
    existing = await session.execute(
        select(Tenant).where(Tenant.tenant_id == body.tenant_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Tenant '{body.tenant_id}' already exists")

    api_key = secrets.token_hex(32)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    schema_name = f"tenant_{body.tenant_id}"
    s3_prefix = f"tenants/{body.tenant_id}/"

    tenant = Tenant(
        tenant_id=body.tenant_id,
        name=body.name,
        api_key_hash=api_key_hash,
        schema_name=schema_name,
        s3_prefix=s3_prefix,
        config=body.config,
        is_active=True,
    )
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    # Provision the per-tenant PostgreSQL schema + tables
    await create_tenant_schema(schema_name)

    logger.info(
        "admin.create_tenant",
        extra={"tenant_id": body.tenant_id, "schema": schema_name},
    )

    return TenantCreateResponse(
        id=tenant.id,
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        schema_name=tenant.schema_name,
        s3_prefix=tenant.s3_prefix,
        config=tenant.config,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
        api_key=api_key,
    )


@router.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(
    _: None = Depends(get_admin),
    session: AsyncSession = Depends(get_db),
) -> list[TenantResponse]:
    """List all tenants (including inactive)."""
    result = await session.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    tenants = result.scalars().all()
    return [_tenant_to_response(t) for t in tenants]


@router.patch("/tenants/{tenant_id}", response_model=TenantResponse)
async def patch_tenant(
    tenant_id: UUID,
    body: TenantPatch,
    _: None = Depends(get_admin),
    session: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """Update a tenant's config (merged, not replaced) and/or is_active flag."""
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if body.config is not None:
        # Merge new keys into existing config (don't wholesale replace)
        merged = dict(tenant.config or {})
        merged.update(body.config)
        tenant.config = merged

    if body.is_active is not None:
        tenant.is_active = body.is_active

    await session.commit()
    await session.refresh(tenant)

    logger.info(
        "admin.patch_tenant",
        extra={"tenant_id": str(tenant_id)},
    )
    return _tenant_to_response(tenant)
