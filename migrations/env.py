from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Import Base and all models so Alembic can detect them
from app.config import settings
from app.db.models import Base, Tenant  # noqa: F401 — registers model with metadata

# Alembic Config object
config = context.config

# Set up loggers if a config file is present
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Only manage the public schema (Tenant model).
# Per-tenant schemas are managed by create_tenant_schema() in seed_tenant.py.
target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Include only objects that belong to the public schema."""
    if type_ == "table":
        return getattr(object, "schema", None) == "public"
    return True


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL script)."""
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_object=include_object,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
