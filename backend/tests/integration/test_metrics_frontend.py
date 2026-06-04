"""POST /metrics/frontend (no session cookie required)."""

import pytest
from httpx import ASGITransport, AsyncClient

from agent_factory.infra.prometheus_registry import AF_FRONTEND_EVENTS_TOTAL
from agent_factory.main import create_app


@pytest.fixture
async def client():
    app = create_app(enable_prometheus=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_metrics_frontend_accepts_beacon_payload(client):
    m = AF_FRONTEND_EVENTS_TOTAL.labels(
        event_type="page_load",
        agent_id="demo-agent",
    )
    before = m._value.get()
    r = await client.post(
        "/api/v1/metrics/frontend",
        json={
            "agent_id": "demo-agent",
            "event_type": "page_load",
            "duration_ms": 120,
            "payload": {"route": "/apps/demo"},
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"
    assert m._value.get() == before + 1


@pytest.mark.asyncio
async def test_metrics_frontend_requires_event_type(client):
    r = await client.post(
        "/api/v1/metrics/frontend",
        json={"agent_id": "x"},
    )
    assert r.status_code == 422
