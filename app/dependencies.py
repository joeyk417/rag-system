from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_admin_key, verify_api_key
from app.db.models import Tenant
from app.db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session per request."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_tenant(
    x_api_key: str = Header(..., alias="X-API-Key"),
    session: AsyncSession = Depends(get_db),
) -> Tenant:
    """Validate X-API-Key header and return the matching active Tenant."""
    return await verify_api_key(x_api_key, session)


async def get_admin(
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> None:
    """Validate X-Admin-Key header (admin-only endpoints)."""
    verify_admin_key(x_admin_key)
