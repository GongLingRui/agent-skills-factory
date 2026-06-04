"""Integration tests for auth exchange -> session flow."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from agent_factory.main import create_app


@pytest.fixture
async def client(monkeypatch):
    # Ensure test secrets are set before the app imports settings
    monkeypatch.setenv("JWT_SECRET", "x" * 32 + "-short-jwt-secret-test")
    monkeypatch.setenv("PORTAL_JWT_SECRET", "x" * 32 + "-portal-secret-test")
    monkeypatch.setenv("JWT_EXPIRE_SECONDS", "60")
    monkeypatch.setenv("USER_ID_HASH_SALT", "test-salt")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("DEV_WIDGET_AUTH_BYPASS", "false")

    # Clear lru_cache so new env vars are picked up
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()

    app = create_app(enable_prometheus=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_auth_exchange_invalid_header(client):
    r = await client.post(
        "/api/v1/auth/exchange",
        json={"agent_id": "demo"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_api_status(client):
    r = await client.get("/api/v1/status")
    assert r.status_code == 200
    data = r.json()
    assert data["api"] == "v1"


@pytest.mark.asyncio
async def test_auth_me_requires_cookie(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_auth_dev_session_disabled_by_default(client):
    r = await client.post(
        "/api/v1/auth/dev/session",
        json={"agent_id": "demo-agent"},
    )
    assert r.status_code == 403
