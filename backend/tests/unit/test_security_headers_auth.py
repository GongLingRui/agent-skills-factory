"""Security headers on auth routes (信息安全 §6.2 Web)."""

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from agent_factory.middleware.security_headers import SecurityHeadersMiddleware


async def _ok(_request):
    return PlainTextResponse("ok")


def test_cache_control_no_store_on_auth_paths():
    app = Starlette(
        routes=[
            Route("/api/v1/auth/session", _ok),
            Route("/api/v1/agents", _ok),
        ]
    )
    app.add_middleware(SecurityHeadersMiddleware)
    client = TestClient(app)
    r1 = client.get("/api/v1/auth/session")
    assert "no-store" in r1.headers.get("cache-control", "").lower()
    r2 = client.get("/api/v1/agents")
    assert r2.headers.get("cache-control") is None
