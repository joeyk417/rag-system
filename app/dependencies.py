from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.providers.base import BaseLLMProvider
from app.core.providers.openai_provider import OpenAIProvider
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


def get_provider(tenant: Tenant = Depends(get_tenant)) -> BaseLLMProvider:
    """Return the appropriate LLM provider for this tenant.

    Phase 1: always returns OpenAIProvider.
    Phase 2 (data_sovereignty=AU): will return BedrockProvider — see docs/phase2-aws.md.
    """
    # TODO Phase 2: if tenant.config.get("data_sovereignty") == "AU": return BedrockProvider()
    return OpenAIProvider()
