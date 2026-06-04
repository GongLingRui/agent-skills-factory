"""Admin degradation API (Bearer ADMIN_API_TOKEN)."""

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
async def test_admin_recover_401_when_no_bearer_or_session(client_admin_disabled):
    r = await client_admin_disabled.post("/api/v1/admin/degradation/recover")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "SESSION_REQUIRED"


@pytest.mark.asyncio
async def test_admin_recover_401_wrong_bearer_without_session(
    client_admin_configured,
):
    r = await client_admin_configured.post(
        "/api/v1/admin/degradation/recover",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_recover_ok(client_admin_configured):
    r = await client_admin_configured.post(
        "/api/v1/admin/degradation/recover",
        headers={"Authorization": "Bearer secret-admin-token-for-tests"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["level"] == 0


@pytest.mark.asyncio
async def test_admin_set_level_ok(client_admin_configured):
    r = await client_admin_configured.post(
        "/api/v1/admin/degradation/level",
        headers={"Authorization": "Bearer secret-admin-token-for-tests"},
        json={"level": 2, "reason": "test", "duration_minutes": 5},
    )
    assert r.status_code == 200
    assert r.json()["level"] == 2


@pytest.mark.asyncio
async def test_admin_product_metrics_requires_query_dates(client_admin_configured):
    r = await client_admin_configured.get(
        "/api/v1/admin/product-metrics/summary",
        headers={"Authorization": "Bearer secret-admin-token-for-tests"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_admin_product_metrics_invalid_range(client_admin_configured):
    r = await client_admin_configured.get(
        "/api/v1/admin/product-metrics/summary",
        headers={"Authorization": "Bearer secret-admin-token-for-tests"},
        params={
            "start_date": "2026-05-10",
            "end_date": "2026-05-01",
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_admin_session_revocations_ok(client_admin_configured):
    h = "a" * 64
    r = await client_admin_configured.post(
        "/api/v1/admin/session-revocations",
        headers={"Authorization": "Bearer secret-admin-token-for-tests"},
        json={"user_id_hash": h},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert int(body["revoke_generation"]) >= 1


@pytest.mark.asyncio
async def test_admin_session_revocations_503_when_admin_disabled(
    client_admin_disabled,
):
    r = await client_admin_disabled.post(
        "/api/v1/admin/session-revocations",
        json={"user_id_hash": "b" * 64},
    )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_admin_product_metrics_ok_empty(client_admin_configured):
    r = await client_admin_configured.get(
        "/api/v1/admin/product-metrics/summary",
        headers={"Authorization": "Bearer secret-admin-token-for-tests"},
        params={
            "start_date": "2026-01-01",
            "end_date": "2026-01-07",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["start_date"] == "2026-01-01"
    assert "feedback" in body
