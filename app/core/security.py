from __future__ import annotations

import hashlib
import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Tenant


async def verify_api_key(key: str, session: AsyncSession) -> Tenant:
    """Hash the key and look it up in public.tenants. Raises 401 if not found or inactive."""
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    result = await session.execute(
        select(Tenant).where(
            Tenant.api_key_hash == key_hash,
            Tenant.is_active.is_(True),
        )
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return tenant


def verify_admin_key(key: str) -> None:
    """Constant-time comparison against the admin API key. Raises 403 on mismatch."""
    if not settings.admin_api_key or not secrets.compare_digest(key, settings.admin_api_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")
