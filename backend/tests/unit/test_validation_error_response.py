"""422 validation responses (信息安全 §6.2)."""

import pytest
from httpx import ASGITransport, AsyncClient

from agent_factory.config import get_settings
from agent_factory.main import create_app


@pytest.mark.asyncio
async def test_validation_production_hides_details(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        app = create_app(enable_prometheus=False)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/auth/exchange", json={})
        assert r.status_code == 422
        err = r.json().get("error") or {}
        assert err.get("code") == "VALIDATION_ERROR"
        assert "details" not in err
    finally:
        monkeypatch.delenv("APP_ENV", raising=False)
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_validation_development_includes_details(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    try:
        app = create_app(enable_prometheus=False)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/auth/exchange", json={})
        assert r.status_code == 422
        err = r.json().get("error") or {}
        assert err.get("code") == "VALIDATION_ERROR"
        assert "details" in err
    finally:
        monkeypatch.delenv("APP_ENV", raising=False)
        get_settings.cache_clear()
