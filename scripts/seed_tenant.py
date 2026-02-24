from __future__ import annotations

"""seed_tenant.py — Create the Elastomers Australia tenant.

Run after setup_db.py:
    python scripts/seed_tenant.py

Creates:
  - public.tenants row for EA
  - tenant_elastomers_au schema
  - documents, chunks, ingest_jobs tables with all indexes
  - Prints generated API key to stdout — save it, it won't be shown again
"""

import asyncio
import hashlib
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg

from app.config import settings

_DB_URL = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

_TENANT_ID = "elastomers_au"
_TENANT_NAME = "Elastomers Australia"
_SCHEMA_NAME = "tenant_elastomers_au"
_S3_PREFIX = "tenants/elastomers_au/"
_TENANT_CONFIG = {
    "doc_number_pattern": r"^(EA-[A-Z-]+-\d+)",
    "restricted_doc_types": ["ENG-MAT"],
    "data_sovereignty": "AU",
}


async def create_tenant_schema(conn: asyncpg.Connection, schema: str) -> None:
    """Create per-tenant schema and all tables/indexes."""
    print(f"  Creating schema {schema!r} …")
    await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")

    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.documents (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            file_hash       TEXT NOT NULL UNIQUE,
            filename        TEXT NOT NULL,
            s3_key          TEXT NOT NULL,
            doc_number      TEXT,
            doc_type        TEXT,
            revision        TEXT,
            title           TEXT,
            classification  TEXT,
            extra_metadata  JSONB NOT NULL DEFAULT '{{}}',
            page_count      INTEGER,
            status          TEXT NOT NULL DEFAULT 'pending',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.chunks (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id     UUID NOT NULL REFERENCES {schema}.documents(id) ON DELETE CASCADE,
            page_number     INTEGER NOT NULL,
            chunk_index     INTEGER NOT NULL,
            heading         TEXT,
            content         TEXT NOT NULL,
            embedding       vector(1536),
            token_count     INTEGER,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.ingest_jobs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id     UUID,
            status          TEXT NOT NULL DEFAULT 'pending',
            error           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # pgvector ivfflat index — requires at least one row to build, so use IF NOT EXISTS
    await conn.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding
            ON {schema}.chunks
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
    """)

    await conn.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_chunks_document_id
            ON {schema}.chunks (document_id);
    """)

    await conn.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_documents_doc_type
            ON {schema}.documents (doc_type);
    """)

    print(f"  ✓ Schema {schema!r} ready.")


async def main() -> None:
    api_key = secrets.token_hex(32)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    print(f"Connecting to database …")
    conn = await asyncpg.connect(_DB_URL)
    try:
        # Check if tenant already exists
        existing = await conn.fetchval(
            "SELECT tenant_id FROM public.tenants WHERE tenant_id = $1", _TENANT_ID
        )
        if existing:
            print(f"Tenant {_TENANT_ID!r} already exists — skipping insert.")
        else:
            import json
            await conn.execute(
                """
                INSERT INTO public.tenants
                    (tenant_id, name, api_key_hash, schema_name, s3_prefix, config)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                _TENANT_ID,
                _TENANT_NAME,
                api_key_hash,
                _SCHEMA_NAME,
                _S3_PREFIX,
                json.dumps(_TENANT_CONFIG),
            )
            print(f"✓ Tenant {_TENANT_ID!r} inserted.")

        await create_tenant_schema(conn, _SCHEMA_NAME)

        if not existing:
            print()
            print("=" * 60)
            print("  EA TENANT API KEY (save this — shown only once)")
            print(f"  {api_key}")
            print("=" * 60)
        else:
            print("(API key unchanged — use the key generated on first run)")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
