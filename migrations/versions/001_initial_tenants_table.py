"""Create public.tenants table

Revision ID: 001
Revises:
Create Date: 2026-02-24

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use raw SQL so this migration is idempotent whether or not setup_db.py was run first.
    op.execute("""
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
        )
    """)


def downgrade() -> None:
    op.drop_table("tenants", schema="public")
