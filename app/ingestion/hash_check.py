from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document


def compute_hash(pdf_bytes: bytes) -> str:
    """Return SHA-256 hex digest of raw PDF bytes."""
    return hashlib.sha256(pdf_bytes).hexdigest()


async def find_existing(file_hash: str, session: AsyncSession) -> uuid.UUID | None:
    """Return the document_id if a document with this hash already exists, else None."""
    result = await session.execute(
        select(Document.id).where(Document.file_hash == file_hash).limit(1)
    )
    row = result.scalar_one_or_none()
    return row
