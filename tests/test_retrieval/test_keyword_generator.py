from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.retrieval.keyword_generator import generate


def _make_tenant(config: dict | None = None) -> MagicMock:
    tenant = MagicMock()
    tenant.name = "Test Tenant"
    tenant.config = config or {}
    return tenant


def _make_provider(json_response: dict) -> MagicMock:
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=(json.dumps(json_response), None))
    return provider


@pytest.mark.asyncio
async def test_generate_returns_five_keywords() -> None:
    keywords = ["installation procedure", "installation steps", "screen panel", "tensioning", "assembly"]
    provider = _make_provider({"keywords": keywords})
    result = await generate("screen installation steps", _make_tenant(), provider)
    assert result == keywords
    assert len(result) == 5


@pytest.mark.asyncio
async def test_generate_fallback_on_parse_error() -> None:
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=("invalid json{{", None))
    result = await generate("bolt torque procedure", _make_tenant(), provider)
    # Falls back to query token split
    assert result == ["bolt", "torque", "procedure"]


@pytest.mark.asyncio
async def test_generate_fallback_on_llm_error() -> None:
    provider = MagicMock()
    provider.generate = AsyncMock(side_effect=RuntimeError("LLM error"))
    result = await generate("screen panel dimensions", _make_tenant(), provider)
    assert result == ["screen", "panel", "dimensions"]


@pytest.mark.asyncio
async def test_generate_fallback_truncates_to_five_tokens() -> None:
    provider = MagicMock()
    provider.generate = AsyncMock(side_effect=RuntimeError("LLM error"))
    result = await generate("one two three four five six seven", _make_tenant(), provider)
    assert len(result) <= 5


@pytest.mark.asyncio
async def test_generate_uses_tenant_domain_in_prompt() -> None:
    keywords = ["k1", "k2", "k3", "k4", "k5"]
    provider = _make_provider({"keywords": keywords})
    tenant = _make_tenant(config={"domain": "mining screen media"})
    await generate("rubber compound", tenant, provider)
    call_args = provider.generate.call_args
    assert "mining screen media" in call_args[0][0]  # system_prompt


@pytest.mark.asyncio
async def test_generate_uses_domain_hints_in_prompt() -> None:
    keywords = ["k1", "k2", "k3", "k4", "k5"]
    provider = _make_provider({"keywords": keywords})
    tenant = _make_tenant(config={"keyword_hints": ["tensile strength", "compound grade"]})
    await generate("rubber formulation", tenant, provider)
    call_args = provider.generate.call_args
    assert "tensile strength" in call_args[0][0]
