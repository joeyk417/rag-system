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


def tenant_session(session: AsyncSession, schema_name: str) -> AsyncSession:
    """Return a session scoped to the given tenant schema.

    Uses SQLAlchemy's schema_translate_map to route all queries for
    per-tenant models (Document, Chunk, IngestJob) to the correct schema.

    Usage::

        ts = tenant_session(session, tenant.schema_name)
        result = await ts.execute(select(Document))
    """
    return session.execution_options(schema_translate_map={None: schema_name})
