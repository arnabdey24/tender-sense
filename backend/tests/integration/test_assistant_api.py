"""Conversation persistence, tenant isolation, and duplicate-request protection."""

from uuid import uuid4

from httpx import AsyncClient

from app.modules.tenders.models import Tender
from tests.integration.test_rules_decisions_api import (
    Tenant,
    drop_tenant,
    make_tenant,
)
from tests.integration.test_rules_decisions_api import (
    api as api,
)
from tests.integration.test_rules_decisions_api import (
    tenant as tenant,
)
from tests.integration.test_rules_decisions_api import (
    tender as tender,
)


async def test_stream_is_saved_in_order_and_replayed_once(
    api: AsyncClient, tenant: Tenant, tender: Tender
) -> None:
    created = await api.post(
        "/api/v1/assistant/conversations",
        headers=tenant.headers,
        json={"tender_id": str(tender.id)},
    )
    assert created.status_code == 201, created.text
    path = f"/api/v1/assistant/conversations/{created.json()['id']}"
    body = {
        "request_id": str(uuid4()),
        "text": "Show the timeline",
        "artifact": {"kind": "timeline"},
    }
    first = await api.post(path + "/turns", headers=tenant.headers, json=body)
    assert first.status_code == 200, first.text
    assert '"type":"artifact"' in first.text
    assert '"type":"complete"' in first.text
    second = await api.post(path + "/turns", headers=tenant.headers, json=body)
    assert second.status_code == 200
    detail = (await api.get(path, headers=tenant.headers)).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["status"] == "complete"
    assert detail["messages"][1]["artifacts"][0]["kind"] == "timeline"
    assert detail["messages"][1]["context_version"]
    assert (await api.delete(path, headers=tenant.headers)).status_code == 204
    assert (await api.get(path, headers=tenant.headers)).status_code == 404


async def test_other_tenant_cannot_read_delete_or_generate(
    api: AsyncClient, tenant: Tenant, tender: Tender
) -> None:
    created = await api.post(
        "/api/v1/assistant/conversations",
        headers=tenant.headers,
        json={"tender_id": str(tender.id)},
    )
    path = f"/api/v1/assistant/conversations/{created.json()['id']}"
    other = await make_tenant(name="OtherAssistantOrg")
    try:
        assert (await api.get(path, headers=other.headers)).status_code == 404
        assert (await api.delete(path, headers=other.headers)).status_code == 404
        assert (
            await api.post(
                path + "/turns",
                headers=other.headers,
                json={"request_id": str(uuid4()), "text": "Tell me their turnover"},
            )
        ).status_code == 404
        listed = (await api.get("/api/v1/assistant/conversations", headers=other.headers)).json()
        assert created.json()["id"] not in [c["id"] for c in listed]
    finally:
        await drop_tenant(other)


async def test_voice_unavailable_is_explicit(
    api: AsyncClient, tenant: Tenant, tender: Tender
) -> None:
    caps = (await api.get("/api/v1/assistant/capabilities", headers=tenant.headers)).json()
    assert caps["mode"] == "demo"
    assert caps["voice_enabled"] is False
    # Not merely off: the panel needs to know which sentence to show, and a
    # greyed button with no explanation is what it showed before it could.
    assert caps["voice_unavailable_reason"] in {
        "assistant_off",
        "voice_off",
        "no_key",
        "provider_not_gemini",
    }
    created = await api.post(
        "/api/v1/assistant/conversations",
        headers=tenant.headers,
        json={"tender_id": str(tender.id)},
    )
    response = await api.post(
        f"/api/v1/assistant/conversations/{created.json()['id']}/voice-ticket",
        headers=tenant.headers,
    )
    assert response.status_code == 409
