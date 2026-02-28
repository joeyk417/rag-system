from __future__ import annotations

"""Integration test — full mocked flow: ingest → poll → chat → list → delete.

All external dependencies (DB, OpenAI, S3) are mocked via FastAPI dependency overrides
and unittest.mock patches. No infrastructure required.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from app.dependencies import get_db, get_provider, get_tenant
from app.main import app
from app.schemas.chat import Source


def _make_tenant() -> MagicMock:
    tenant = MagicMock()
    tenant.tenant_id = "integration_tenant"
    tenant.name = "Integration Test Tenant"
    tenant.schema_name = "tenant_integration"
    tenant.s3_prefix = "tenants/integration/"
    tenant.config = {}
    return tenant


def _make_provider() -> MagicMock:
    return MagicMock()


async def test_ingest_chat_delete_flow() -> None:
    """Full lifecycle: upload PDF → poll → chat → list → delete."""
    tenant = _make_tenant()
    provider = _make_provider()
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()

    # --- Shared mock session factory ---
    ingest_job = MagicMock()
    ingest_job.id = job_id
    ingest_job.status = "completed"
    ingest_job.document_id = doc_id
    ingest_job.error = None
    ingest_job.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ingest_job.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

    doc = MagicMock()
    doc.id = doc_id
    doc.filename = "EA-SOP-001-Screen-Installation.pdf"
    doc.doc_number = "EA-SOP-001"
    doc.doc_type = "SOP"
    doc.revision = "A"
    doc.title = "Screen Installation"
    doc.classification = "STANDARD"
    doc.page_count = 10
    doc.status = "completed"
    doc.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    doc.s3_key = "tenants/integration/EA-SOP-001.pdf"

    # Override dependencies
    app.dependency_overrides[get_tenant] = lambda: tenant
    app.dependency_overrides[get_provider] = lambda: provider

    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

            # Step 1: Upload PDF
            with patch("app.api.v1.ingest.compute_hash", return_value="abc123"), \
                 patch("app.api.v1.ingest.find_existing", new=AsyncMock(return_value=None)), \
                 patch("app.api.v1.ingest.tenant_session") as mock_ts, \
                 patch("app.api.v1.ingest.run_pipeline"):
                mock_session = AsyncMock()
                mock_session.add = MagicMock()
                mock_session.commit = AsyncMock()
                mock_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", job_id))
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_ts.return_value = MagicMock(return_value=mock_session)

                response = await client.post(
                    "/api/v1/ingest",
                    files={"file": ("EA-SOP-001-Screen-Installation.pdf", b"%PDF-1.4 test", "application/pdf")},
                )

            assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"
            ingest_body = response.json()
            assert ingest_body["status"] == "pending"

            # Step 2: Poll job status
            with patch("app.api.v1.ingest.tenant_session") as mock_ts:
                mock_session = AsyncMock()
                mock_session.get = AsyncMock(return_value=ingest_job)
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_ts.return_value = MagicMock(return_value=mock_session)

                response = await client.get(f"/api/v1/ingest/{job_id}")

            assert response.status_code == 200
            status_body = response.json()
            assert status_body["status"] == "completed"
            assert status_body["document_id"] == str(doc_id)

            # Step 3: Chat query
            sources = [Source(doc_number="EA-SOP-001", title="Screen Installation", page_number=5, s3_key="ea/sop.pdf")]
            with patch("app.api.v1.chat.run_crag", new=AsyncMock(return_value=("The torque is 370 Nm.", sources))):
                response = await client.post(
                    "/api/v1/chat",
                    json={"query": "What torque for M20 Grade 10.9 bolts lubricated?"},
                )

            assert response.status_code == 200
            chat_body = response.json()
            assert "370" in chat_body["answer"]
            assert len(chat_body["sources"]) == 1

            # Step 4: List documents
            with patch("app.api.v1.documents.tenant_session") as mock_ts:
                mock_session = AsyncMock()
                mock_result = MagicMock()
                mock_result.scalars.return_value.all.return_value = [doc]
                mock_session.execute = AsyncMock(return_value=mock_result)
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_ts.return_value = MagicMock(return_value=mock_session)

                response = await client.get("/api/v1/documents")

            assert response.status_code == 200
            docs_body = response.json()
            assert len(docs_body) == 1
            assert docs_body[0]["doc_number"] == "EA-SOP-001"

            # Step 5: Delete document
            with patch("app.api.v1.documents.tenant_session") as mock_ts:
                mock_session = AsyncMock()
                mock_session.get = AsyncMock(return_value=doc)
                mock_session.delete = AsyncMock()
                mock_session.commit = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_ts.return_value = MagicMock(return_value=mock_session)

                response = await client.delete(f"/api/v1/documents/{doc_id}")

            assert response.status_code == 204
            mock_session.delete.assert_called_once_with(doc)

    finally:
        app.dependency_overrides.clear()
