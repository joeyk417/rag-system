from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.retrieval.filter_extractor import QueryFilters, extract


def _make_tenant(config: dict | None = None) -> MagicMock:
    tenant = MagicMock()
    tenant.config = config or {}
    return tenant


def _make_provider(json_response: dict) -> MagicMock:
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=(json.dumps(json_response), None))
    return provider


@pytest.mark.asyncio
async def test_extract_doc_type() -> None:
    provider = _make_provider({"doc_type": "SOP", "doc_number": None, "classification": None})
    result = await extract("screen installation SOP", _make_tenant(), provider)
    assert result.doc_type == "SOP"
    assert result.doc_number is None
    assert result.classification is None


@pytest.mark.asyncio
async def test_extract_doc_number() -> None:
    provider = _make_provider({"doc_type": "ENG-DRW", "doc_number": "EA-ENG-DRW-7834", "classification": None})
    result = await extract("EA-ENG-DRW-7834 banana screen", _make_tenant(), provider)
    assert result.doc_type == "ENG-DRW"
    assert result.doc_number == "EA-ENG-DRW-7834"


@pytest.mark.asyncio
async def test_extract_classification() -> None:
    provider = _make_provider({"doc_type": None, "doc_number": None, "classification": "CONFIDENTIAL"})
    result = await extract("show confidential docs", _make_tenant(), provider)
    assert result.classification == "CONFIDENTIAL"


@pytest.mark.asyncio
async def test_extract_all_none() -> None:
    provider = _make_provider({"doc_type": None, "doc_number": None, "classification": None})
    result = await extract("what is the bolt torque?", _make_tenant(), provider)
    assert result == QueryFilters()


@pytest.mark.asyncio
async def test_extract_returns_empty_on_parse_error() -> None:
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=("not valid json{{{", None))
    result = await extract("any query", _make_tenant(), provider)
    assert result == QueryFilters()


@pytest.mark.asyncio
async def test_extract_returns_empty_on_llm_error() -> None:
    provider = MagicMock()
    provider.generate = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    result = await extract("any query", _make_tenant(), provider)
    assert result == QueryFilters()


@pytest.mark.asyncio
async def test_extract_uses_tenant_valid_doc_types() -> None:
    """Provider is called with a system prompt that includes tenant's valid_doc_types."""
    provider = _make_provider({"doc_type": "CUSTOM", "doc_number": None, "classification": None})
    tenant = _make_tenant(config={"valid_doc_types": ["CUSTOM", "SPEC"]})
    result = await extract("show me a CUSTOM doc", tenant, provider)
    call_args = provider.generate.call_args
    assert "CUSTOM" in call_args[0][0]  # system_prompt contains tenant doc types
    assert result.doc_type == "CUSTOM"
