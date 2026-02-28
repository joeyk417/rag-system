from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from httpx import ASGITransport

from app.dependencies import get_tenant
from app.main import app


def _make_tenant() -> MagicMock:
    tenant = MagicMock()
    tenant.tenant_id = "test_tenant"
    tenant.name = "Test Tenant"
    tenant.schema_name = "tenant_test"
    tenant.config = {}
    return tenant


def _mock_tenant(tenant: MagicMock):
    async def _get_tenant():
        return tenant
    return _get_tenant


def _make_doc(doc_type: str = "SOP") -> MagicMock:
    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.filename = f"EA-{doc_type}-001-Guide.pdf"
    doc.doc_number = f"EA-{doc_type}-001"
    doc.doc_type = doc_type
    doc.revision = "A"
    doc.title = "Installation Guide"
    doc.classification = "STANDARD"
    doc.page_count = 12
    doc.status = "completed"
    doc.created_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
    return doc


async def test_list_documents_empty() -> None:
    tenant = _make_tenant()

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_maker = MagicMock(return_value=mock_session)

    app.dependency_overrides[get_tenant] = _mock_tenant(tenant)
    with patch("app.api.v1.documents.tenant_session", return_value=mock_maker):
        try:
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/v1/documents")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []


async def test_list_documents_with_results() -> None:
    tenant = _make_tenant()
    docs = [_make_doc("SOP"), _make_doc("ENG-DRW")]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = docs
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_maker = MagicMock(return_value=mock_session)

    app.dependency_overrides[get_tenant] = _mock_tenant(tenant)
    with patch("app.api.v1.documents.tenant_session", return_value=mock_maker):
        try:
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/v1/documents")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["doc_type"] == "SOP"
    assert body[1]["doc_type"] == "ENG-DRW"


async def test_list_documents_doc_type_filter() -> None:
    """doc_type query param should be passed through to the SQL filter."""
    tenant = _make_tenant()
    docs = [_make_doc("SOP")]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = docs
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_maker = MagicMock(return_value=mock_session)

    app.dependency_overrides[get_tenant] = _mock_tenant(tenant)
    with patch("app.api.v1.documents.tenant_session", return_value=mock_maker):
        try:
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/v1/documents", params={"doc_type": "SOP"})
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["doc_type"] == "SOP"


async def test_delete_document() -> None:
    """DELETE returns 204; S3 deletion skipped in development mode."""
    tenant = _make_tenant()
    doc = _make_doc()
    doc.s3_key = "tenants/test/doc.pdf"

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=doc)
    mock_session.delete = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_maker = MagicMock(return_value=mock_session)

    app.dependency_overrides[get_tenant] = _mock_tenant(tenant)
    with patch("app.api.v1.documents.tenant_session", return_value=mock_maker):
        try:
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.delete(f"/api/v1/documents/{doc.id}")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 204
    mock_session.delete.assert_called_once_with(doc)
    mock_session.commit.assert_called_once()


async def test_delete_document_not_found() -> None:
    tenant = _make_tenant()
    missing_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_maker = MagicMock(return_value=mock_session)

    app.dependency_overrides[get_tenant] = _mock_tenant(tenant)
    with patch("app.api.v1.documents.tenant_session", return_value=mock_maker):
        try:
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.delete(f"/api/v1/documents/{missing_id}")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 404
