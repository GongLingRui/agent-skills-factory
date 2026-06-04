"""Security-related HTTP response headers."""

from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from agent_factory.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline headers (PRD / docs/30)."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        response = await call_next(request)
        if "server" in response.headers:
            del response.headers["server"]
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        hsts = get_settings().HSTS_MAX_AGE_SECONDS
        if hsts > 0:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={hsts}; includeSubDomains",
            )
        path = request.url.path
        if path.startswith("/api/v1/auth/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response
