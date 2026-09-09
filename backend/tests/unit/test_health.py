from __future__ import annotations

from httpx import AsyncClient


async def test_liveness_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unknown_route_uses_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_openapi_document_is_served(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/health/live" in response.json()["paths"]
