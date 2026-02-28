from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ingestion.hash_check import compute_hash, find_existing


def test_compute_hash_deterministic() -> None:
    data = b"hello world"
    assert compute_hash(data) == compute_hash(data)


def test_compute_hash_differs_for_different_content() -> None:
    assert compute_hash(b"file A content") != compute_hash(b"file B content")


def test_compute_hash_is_sha256_hex() -> None:
    result = compute_hash(b"test")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


@pytest.mark.asyncio
async def test_new_hash_returns_none() -> None:
    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)

    result = await find_existing("nonexistent_hash", session)
    assert result is None


@pytest.mark.asyncio
async def test_existing_hash_returns_document_id() -> None:
    existing_id = uuid.uuid4()
    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = existing_id
    session.execute = AsyncMock(return_value=execute_result)

    result = await find_existing("some_hash", session)
    assert result == existing_id
