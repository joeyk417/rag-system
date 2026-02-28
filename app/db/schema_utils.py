from __future__ import annotations

import logging

from sqlalchemy import text

from app.db.session import async_engine

logger = logging.getLogger(__name__)


async def create_tenant_schema(schema_name: str) -> None:
    """Create per-tenant PostgreSQL schema with all required tables and indexes.

    DDL is idempotent (IF NOT EXISTS) so safe to re-run.
    Mirrors the SQL in scripts/seed_tenant.py but uses SQLAlchemy text() so it
    runs through the existing async_engine without a direct asyncpg dependency.
    """
    logger.info("schema_utils.create_tenant_schema", extra={"schema": schema_name})

    async with async_engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))

        await conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.documents (
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
            )
        """))

        await conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.chunks (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id     UUID NOT NULL
                                    REFERENCES {schema_name}.documents(id)
                                    ON DELETE CASCADE,
                page_number     INTEGER NOT NULL,
                chunk_index     INTEGER NOT NULL,
                heading         TEXT,
                content         TEXT NOT NULL,
                embedding       vector(1536),
                token_count     INTEGER,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        await conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.ingest_jobs (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id     UUID,
                status          TEXT NOT NULL DEFAULT 'pending',
                error           TEXT,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        await conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema_name}_chunks_embedding
                ON {schema_name}.chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
        """))

        await conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema_name}_chunks_document_id
                ON {schema_name}.chunks (document_id)
        """))

        await conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema_name}_documents_doc_type
                ON {schema_name}.documents (doc_type)
        """))

    logger.info("schema_utils.create_tenant_schema.done", extra={"schema": schema_name})
