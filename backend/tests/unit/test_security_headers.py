"""P0.5: SecurityHeadersMiddleware baseline (align docs/45, plan §5)."""

from __future__ import annotations

from starlette.testclient import TestClient

from agent_factory.main import create_app


def test_security_headers_on_health() -> None:
    app = create_app(enable_prometheus=False)
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    h = r.headers
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("Referrer-Policy") == "no-referrer"
    assert "camera=()" in (h.get("Permissions-Policy") or "")
