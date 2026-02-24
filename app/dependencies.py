from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session per request."""
    async with AsyncSessionLocal() as session:
        yield session


# TODO: implement in Task 3
# async def get_tenant(
#     x_api_key: str = Header(..., alias="X-API-Key"),
#     session: AsyncSession = Depends(get_db),
# ) -> Tenant:
#     """Validate X-API-Key and return the matching active Tenant."""
#     key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
#     result = await session.execute(
#         select(Tenant).where(Tenant.api_key_hash == key_hash, Tenant.is_active.is_(True))
#     )
#     tenant = result.scalar_one_or_none()
#     if tenant is None:
#         raise HTTPException(status_code=401, detail="Invalid or inactive API key")
#     return tenant


# TODO: implement in Task 3
# async def get_admin(
#     x_admin_key: str = Header(..., alias="X-Admin-Key"),
# ) -> None:
#     """Validate admin API key (used by /admin/* endpoints)."""
#     if not secrets.compare_digest(x_admin_key, settings.admin_api_key):
#         raise HTTPException(status_code=403, detail="Invalid admin key")
