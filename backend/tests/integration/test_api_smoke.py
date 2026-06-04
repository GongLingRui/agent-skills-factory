"""Smoke tests for FastAPI app startup and basic endpoints (no DB)."""

import pytest
from httpx import ASGITransport, AsyncClient

from agent_factory.main import create_app


@pytest.fixture
async def client():
    app = create_app(enable_prometheus=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_api_status(client):
    r = await client.get("/api/v1/status")
    assert r.status_code == 200
    assert r.json()["api"] == "v1"


@pytest.mark.asyncio
async def test_new_session_requires_session_cookie(client):
    r = await client.post("/api/v1/agents/demo-agent/new-session")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_feedback_requires_session_cookie(client):
    r = await client.post(
        "/api/v1/feedback",
        json={
            "session_id": "sess_x",
            "message_id": "msg_1",
            "run_id": "run_1",
            "agent_id": "demo-agent",
            "feedback": "thumbs_up",
        },
    )
    assert r.status_code == 401
