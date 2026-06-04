"""Audit query API auth matrix (DB-backed responses need live PostgreSQL)."""

import pytest
from httpx import ASGITransport, AsyncClient

from agent_factory.main import create_app


@pytest.fixture
async def client_admin_configured(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "secret-admin-token-for-tests")
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    app = create_app(enable_prometheus=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture
async def client_admin_disabled(monkeypatch):
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    app = create_app(enable_prometheus=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_audit_logs_401_without_session_when_admin_disabled(
    client_admin_disabled,
):
    """无 Cookie 且无 Bearer 时走会话鉴权，返回 401（docs/51）。"""
    r = await client_admin_disabled.get("/api/v1/audit/logs")
    assert r.status_code == 401

    r2 = await client_admin_disabled.get("/api/v1/audit/logs/export")
    assert r2.status_code == 401

    r3 = await client_admin_disabled.get(
        "/api/v1/audit/stats/daily/export",
        params={"start_date": "2026-01-01", "end_date": "2026-01-02"},
    )
    assert r3.status_code == 401


@pytest.mark.asyncio
async def test_audit_logs_401_wrong_bearer_without_session(
    client_admin_configured,
):
    """错误 Bearer 且未带会话 Cookie 时无法通过 require_audit_reader。"""
    r = await client_admin_configured.get(
        "/api/v1/audit/logs",
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401

    r2 = await client_admin_configured.get(
        "/api/v1/audit/logs/export",
        headers={"Authorization": "Bearer wrong"},
    )
    assert r2.status_code == 401

    r3 = await client_admin_configured.get(
        "/api/v1/audit/stats/daily/export",
        params={"start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert r3.status_code == 401


@pytest.mark.asyncio
async def test_audit_daily_requires_dates(client_admin_configured):
    r = await client_admin_configured.get(
        "/api/v1/audit/stats/daily",
        headers={"Authorization": "Bearer secret-admin-token-for-tests"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_audit_sessions_list_401_without_auth(client_admin_disabled):
    r = await client_admin_disabled.get("/api/v1/audit/sessions")
    assert r.status_code == 401
