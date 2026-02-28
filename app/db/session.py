from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

async_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def tenant_session(schema_name: str) -> async_sessionmaker[AsyncSession]:
    """Return a sessionmaker scoped to the given tenant schema.

    Creates a new engine proxy with schema_translate_map applied so all
    queries for per-tenant models (Document, Chunk, IngestJob) are routed
    to the correct schema automatically.

    Usage::

        async with tenant_session(tenant.schema_name)() as ts:
            result = await ts.execute(select(Document))
    """
    tenant_engine = async_engine.execution_options(
        schema_translate_map={None: schema_name}
    )
    return async_sessionmaker(tenant_engine, class_=AsyncSession, expire_on_commit=False)
