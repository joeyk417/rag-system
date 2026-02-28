from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from app.config import settings
from app.dependencies import get_admin, get_db
from app.main import app


def _mock_no_admin():
    """Override get_admin to pass (no validation)."""
    async def _get_admin():
        return None
    return _get_admin


def _make_tenant_row(**kwargs) -> MagicMock:
    t = MagicMock()
    t.id = kwargs.get("id", uuid.uuid4())
    t.tenant_id = kwargs.get("tenant_id", "new_tenant")
    t.name = kwargs.get("name", "New Tenant")
    t.schema_name = kwargs.get("schema_name", "tenant_new_tenant")
    t.s3_prefix = kwargs.get("s3_prefix", "tenants/new_tenant/")
    t.config = kwargs.get("config", {})
    t.is_active = kwargs.get("is_active", True)
    t.created_at = kwargs.get("created_at", datetime(2024, 1, 1, tzinfo=timezone.utc))
    return t


def _make_db_session(scalar_one_or_none=None, scalars_all=None, get_result=None):
    """Build a mock AsyncSession for admin tests."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_one_or_none
    mock_result.scalars.return_value.all.return_value = scalars_all or []
    session.execute = AsyncMock(return_value=mock_result)
    session.get = AsyncMock(return_value=get_result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=lambda obj: None)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _mock_db(session):
    async def _get_db():
        return session
    return _get_db


async def test_create_tenant_wrong_admin_key() -> None:
    """Request with wrong X-Admin-Key returns 403."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/tenants",
            headers={"X-Admin-Key": "definitely-wrong-key"},
            json={"tenant_id": "acme", "name": "ACME Corp"},
        )
    assert response.status_code == 403


async def test_create_tenant() -> None:
    session = _make_db_session(scalar_one_or_none=None)
    tenant_row = _make_tenant_row(tenant_id="acme", name="ACME Corp", schema_name="tenant_acme")
    # After session.refresh, the tenant object should have the right data
    session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", tenant_row.id) or
                                setattr(obj, "created_at", tenant_row.created_at))

    app.dependency_overrides[get_admin] = _mock_no_admin()
    app.dependency_overrides[get_db] = _mock_db(session)
    with patch("app.api.v1.admin.create_tenant_schema", new=AsyncMock()):
        try:
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/admin/tenants",
                    headers={"X-Admin-Key": settings.admin_api_key or "test-admin"},
                    json={"tenant_id": "acme", "name": "ACME Corp", "config": {}},
                )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["tenant_id"] == "acme"
    assert body["schema_name"] == "tenant_acme"
    assert "api_key" in body
    assert len(body["api_key"]) == 64  # secrets.token_hex(32) = 64 hex chars


async def test_create_tenant_duplicate() -> None:
    existing = _make_tenant_row(tenant_id="acme")
    session = _make_db_session(scalar_one_or_none=existing)

    app.dependency_overrides[get_admin] = _mock_no_admin()
    app.dependency_overrides[get_db] = _mock_db(session)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/admin/tenants",
                headers={"X-Admin-Key": settings.admin_api_key or "test-admin"},
                json={"tenant_id": "acme", "name": "ACME Corp"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409


async def test_list_tenants() -> None:
    tenants = [
        _make_tenant_row(tenant_id="acme"),
        _make_tenant_row(tenant_id="beta"),
    ]
    session = _make_db_session(scalars_all=tenants)

    app.dependency_overrides[get_admin] = _mock_no_admin()
    app.dependency_overrides[get_db] = _mock_db(session)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/tenants",
                headers={"X-Admin-Key": settings.admin_api_key or "test-admin"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["tenant_id"] == "acme"
    assert body[1]["tenant_id"] == "beta"


async def test_patch_tenant() -> None:
    tenant_id = uuid.uuid4()
    existing = _make_tenant_row(
        id=tenant_id,
        tenant_id="acme",
        config={"domain": "mining"},
        is_active=True,
    )
    session = _make_db_session(get_result=existing)
    session.refresh = AsyncMock(return_value=None)

    app.dependency_overrides[get_admin] = _mock_no_admin()
    app.dependency_overrides[get_db] = _mock_db(session)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/admin/tenants/{tenant_id}",
                headers={"X-Admin-Key": settings.admin_api_key or "test-admin"},
                json={"config": {"new_key": "new_value"}, "is_active": False},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # Config should be merged (original key preserved + new key added)
    assert existing.config == {"domain": "mining", "new_key": "new_value"}
    assert existing.is_active is False


async def test_patch_tenant_not_found() -> None:
    missing_id = uuid.uuid4()
    session = _make_db_session(get_result=None)

    app.dependency_overrides[get_admin] = _mock_no_admin()
    app.dependency_overrides[get_db] = _mock_db(session)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/admin/tenants/{missing_id}",
                headers={"X-Admin-Key": settings.admin_api_key or "test-admin"},
                json={"is_active": False},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
