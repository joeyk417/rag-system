from __future__ import annotations

"""Tests for the token budget enforcement (Phase 4b).

Mocks the DB session so tests run without a live PostgreSQL instance.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.token_budget import (
    _tier_label,
    check_token_budget,
    get_all_usage,
    record_token_usage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(fetchone_result=None, fetchall_result=None):
    """Return a mock AsyncSession with pre-configured execute results."""
    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = fetchone_result
    result.fetchall.return_value = fetchall_result or []
    session.execute.return_value = result
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# _tier_label
# ---------------------------------------------------------------------------


def test_tier_label_starter():
    assert _tier_label(500_000) == "Starter"
    assert _tier_label(1) == "Starter"


def test_tier_label_professional():
    assert _tier_label(500_001) == "Professional"
    assert _tier_label(2_000_000) == "Professional"


def test_tier_label_enterprise():
    assert _tier_label(2_000_001) == "Enterprise"
    assert _tier_label(10_000_000) == "Enterprise"


# ---------------------------------------------------------------------------
# check_token_budget
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_budget_no_row_allows_request():
    """Fail-open: missing usage row should not block the request."""
    session = _make_session(fetchone_result=None)
    # Should not raise
    await check_token_budget(session, "test_tenant")


@pytest.mark.asyncio
async def test_check_budget_within_quota_passes():
    row = MagicMock()
    row.tokens_used = 100_000
    row.token_quota = 2_000_000
    session = _make_session(fetchone_result=row)
    # Should not raise
    await check_token_budget(session, "test_tenant", estimated_tokens=500)


@pytest.mark.asyncio
async def test_check_budget_exceeded_raises_402():
    row = MagicMock()
    row.tokens_used = 1_999_700
    row.token_quota = 2_000_000
    session = _make_session(fetchone_result=row)
    with pytest.raises(HTTPException) as exc_info:
        await check_token_budget(session, "test_tenant", estimated_tokens=500)
    assert exc_info.value.status_code == 402
    assert "quota" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_check_budget_exactly_at_quota_raises_402():
    row = MagicMock()
    row.tokens_used = 2_000_000
    row.token_quota = 2_000_000
    session = _make_session(fetchone_result=row)
    with pytest.raises(HTTPException) as exc_info:
        await check_token_budget(session, "test_tenant", estimated_tokens=1)
    assert exc_info.value.status_code == 402


# ---------------------------------------------------------------------------
# record_token_usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_token_usage_executes_upsert():
    session = _make_session()
    await record_token_usage(session, "test_tenant", input_tokens=800, output_tokens=434)
    session.execute.assert_called_once()
    session.commit.assert_called_once()
    # Verify the SQL contains the upsert keyword and correct params
    call_args = session.execute.call_args
    sql_str = str(call_args[0][0])
    assert "ON CONFLICT" in sql_str
    params = call_args[0][1]
    assert params["tid"] == "test_tenant"
    assert params["input"] == 800
    assert params["output"] == 434
    assert params["total"] == 1234


# ---------------------------------------------------------------------------
# get_all_usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_usage_returns_formatted_rows():
    from datetime import date

    row = MagicMock()
    row.tenant_id = "elastomers_au"
    row.period_month = date(2026, 3, 1)
    row.tokens_used = 42_300
    row.input_tokens = 30_000
    row.output_tokens = 12_300
    row.token_quota = 10_000_000

    session = _make_session(fetchall_result=[row])
    result = await get_all_usage(session)

    assert len(result) == 1
    r = result[0]
    assert r["tenant_id"] == "elastomers_au"
    assert r["period_month"] == "2026-03-01"
    assert r["tokens_used"] == 42_300
    assert r["input_tokens"] == 30_000
    assert r["output_tokens"] == 12_300
    assert r["token_quota"] == 10_000_000
    assert r["percent_used"] == round(42_300 / 10_000_000 * 100, 2)
    assert r["tier"] == "Enterprise"
    # Cost = input * rate_in + output * rate_out (rates from settings defaults)
    from app.config import settings as s
    expected_cost = round(
        30_000 / 1000 * s.token_cost_input_per_1k
        + 12_300 / 1000 * s.token_cost_output_per_1k,
        4,
    )
    assert r["estimated_cost_usd"] == expected_cost


@pytest.mark.asyncio
async def test_get_all_usage_empty():
    session = _make_session(fetchall_result=[])
    result = await get_all_usage(session)
    assert result == []


# ---------------------------------------------------------------------------
# Integration: POST /chat quota check (API layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_endpoint_returns_402_when_quota_exceeded():
    """Verify that the chat route propagates the 402 from check_token_budget."""
    import uuid
    from datetime import datetime, timezone
    from unittest.mock import patch as mpatch

    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    from app.db.models import Tenant
    from app.main import app

    mock_tenant = Tenant(
        id=uuid.uuid4(),
        tenant_id="elastomers_au",
        name="Elastomers Australia",
        api_key_hash="dummy",
        schema_name="tenant_elastomers_au",
        s3_prefix="tenants/elastomers_au/",
        config={},
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )

    async def _raise_402(*args, **kwargs):
        raise HTTPException(status_code=402, detail="Monthly token quota exceeded")

    # Patch check_token_budget where it's used in the chat module, and stub
    # out verify_api_key so no real DB call is made for auth.
    with (
        mpatch("app.dependencies.verify_api_key", AsyncMock(return_value=mock_tenant)),
        mpatch("app.api.v1.chat.check_token_budget", _raise_402),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/chat",
            json={"query": "What are the PPE requirements?"},
            headers={"X-API-Key": "ea-dev-key-local-testing-only"},
        )
    assert resp.status_code == 402
