from __future__ import annotations

"""setup_db.py — Initialise public database infrastructure.

Run once before seed_tenant.py:
    python scripts/setup_db.py

Creates:
  - pgvector extension
  - public.tenants table
  - public.tenant_usage table (token quota tracking)

Per-tenant schemas/tables are created by seed_tenant.py (or POST /admin/tenants in Task 6).
"""

import asyncio
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg

from app.config import settings

# Convert asyncpg URL to plain postgres URL for asyncpg.connect()
_DB_URL = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

_CREATE_TENANTS_TABLE = """
CREATE TABLE IF NOT EXISTS public.tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    api_key_hash    TEXT NOT NULL,
    schema_name     TEXT NOT NULL,
    s3_prefix       TEXT NOT NULL,
    config          JSONB NOT NULL DEFAULT '{}',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_TENANT_USAGE_TABLE = """
CREATE TABLE IF NOT EXISTS public.tenant_usage (
    tenant_id     TEXT   NOT NULL REFERENCES public.tenants(tenant_id),
    period_month  DATE   NOT NULL,  -- first day of the month e.g. 2026-03-01
    tokens_used   BIGINT NOT NULL DEFAULT 0,
    input_tokens  BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    token_quota   BIGINT NOT NULL,  -- set per subscription tier on onboarding
    PRIMARY KEY (tenant_id, period_month)
);
"""

# Idempotent column additions for existing deployments that pre-date these columns.
_MIGRATE_TENANT_USAGE_COLUMNS = """
ALTER TABLE public.tenant_usage
    ADD COLUMN IF NOT EXISTS input_tokens  BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS output_tokens BIGINT NOT NULL DEFAULT 0;
"""


async def main() -> None:
    print(f"Connecting to {_DB_URL!r} …")
    conn = await asyncpg.connect(_DB_URL)
    try:
        print("Enabling pgvector extension …")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        print("Creating public.tenants table …")
        await conn.execute(_CREATE_TENANTS_TABLE)

        print("Creating/updating public.tenant_usage table …")
        await conn.execute(_CREATE_TENANT_USAGE_TABLE)
        await conn.execute(_MIGRATE_TENANT_USAGE_COLUMNS)

        print("✓ Database setup complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
