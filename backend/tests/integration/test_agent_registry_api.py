"""Agent registry admin API auth (no live PostgreSQL required)."""

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
async def test_create_agent_401_when_no_bearer_and_no_session(client_admin_disabled):
    """注册中心写接口走 ``require_registry_operator``：无运维令牌且无会话 → 401。"""
    r = await client_admin_disabled.post(
        "/api/v1/agents",
        json={"id": "x", "name": "X", "version": "1", "skill": {"id": "s"}},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_agent_401_wrong_bearer_without_session(client_admin_configured):
    """错误 Bearer 且不带会话 Cookie 时无法视为已认证。"""
    r = await client_admin_configured.post(
        "/api/v1/agents",
        headers={"Authorization": "Bearer wrong"},
        json={"id": "x", "name": "X", "version": "1", "skill": {"id": "s"}},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_versions_401_wrong_bearer_without_session(client_admin_configured):
    r = await client_admin_configured.get(
        "/api/v1/agents/demo-agent/versions",
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401
