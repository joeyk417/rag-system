from __future__ import annotations

import httpx
from httpx import ASGITransport

from app.main import app


async def test_health_returns_ok() -> None:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["env"] == "development"
