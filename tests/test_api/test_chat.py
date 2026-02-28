from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from httpx import ASGITransport

from app.dependencies import get_provider, get_tenant
from app.main import app
from app.schemas.chat import Source


def _make_tenant() -> MagicMock:
    tenant = MagicMock()
    tenant.tenant_id = "test_tenant"
    tenant.name = "Test Tenant"
    tenant.schema_name = "tenant_test"
    tenant.config = {}
    return tenant


def _make_provider() -> MagicMock:
    return MagicMock()


def _mock_tenant(tenant: MagicMock):
    async def _get_tenant():
        return tenant
    return _get_tenant


def _mock_provider(provider: MagicMock):
    def _get_provider():
        return provider
    return _get_provider


async def test_chat_returns_answer() -> None:
    tenant = _make_tenant()
    provider = _make_provider()
    sources = [Source(doc_number="EA-SOP-001", title="Guide", page_number=3, s3_key="ea/sop.pdf")]

    with patch("app.api.v1.chat.run_crag", new=AsyncMock(return_value=("The torque is 370 Nm.", sources))):
        app.dependency_overrides[get_tenant] = _mock_tenant(tenant)
        app.dependency_overrides[get_provider] = _mock_provider(provider)
        try:
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/chat",
                    json={"query": "What torque for M20 bolts?"},
                )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "The torque is 370 Nm."
    assert body["query"] == "What torque for M20 bolts?"
    assert len(body["sources"]) == 1
    assert body["sources"][0]["doc_number"] == "EA-SOP-001"


async def test_chat_empty_query() -> None:
    tenant = _make_tenant()
    provider = _make_provider()
    app.dependency_overrides[get_tenant] = _mock_tenant(tenant)
    app.dependency_overrides[get_provider] = _mock_provider(provider)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/chat", json={"query": ""})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


async def test_chat_query_too_long() -> None:
    tenant = _make_tenant()
    provider = _make_provider()
    app.dependency_overrides[get_tenant] = _mock_tenant(tenant)
    app.dependency_overrides[get_provider] = _mock_provider(provider)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/chat", json={"query": "x" * 2001})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


async def test_chat_invalid_api_key() -> None:
    async def _bad_tenant():
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    app.dependency_overrides[get_tenant] = _bad_tenant
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat",
                headers={"X-API-Key": "bad-key"},
                json={"query": "test"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
