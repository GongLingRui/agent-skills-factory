"""Entry rate limiting (IP bucket in Redis)."""

import time
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agent_factory.config import get_settings
from agent_factory.infra.redis import get_redis
from agent_factory.middleware.error_handler import error_body

_EXEMPT_PREFIXES = (
    "/health",
    "/ready",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/feishu/events",
)

_AUTH_STRICT_PATHS = frozenset(
    {
        "/api/v1/auth/exchange",
        "/api/v1/auth/session",
        "/api/v1/auth/sync-permissions",
    }
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed window per minute per client IP (PRD entry limiter)."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in _EXEMPT_PREFIXES):
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)

        s = get_settings()
        client_host = request.client.host if request.client else "unknown"
        window = int(time.time()) // 60
        key = f"rl:ip:{client_host}:{window}"
        auth_limit = s.AUTH_RATE_LIMIT_PER_MINUTE
        auth_key = f"rl:auth_ip:{client_host}:{window}"
        try:
            redis = get_redis()
            n = await redis.incr(key)
            if n == 1:
                await redis.expire(key, 70)
            if n > s.RATE_LIMIT_IP:
                rid = getattr(request.state, "trace_id", "unknown")
                return JSONResponse(
                    status_code=429,
                    content=error_body(
                        "RATE_LIMITED",
                        "Rate limit exceeded",
                        rid,
                    ),
                )
            if path in _AUTH_STRICT_PATHS:
                an = await redis.incr(auth_key)
                if an == 1:
                    await redis.expire(auth_key, 70)
                if an > auth_limit:
                    rid = getattr(request.state, "trace_id", "unknown")
                    return JSONResponse(
                        status_code=429,
                        content=error_body(
                            "AUTH_RATE_LIMITED",
                            "Too many authentication requests",
                            rid,
                        ),
                    )
        except Exception:
            # Degrade open: if Redis is down, do not block traffic
            pass

        return await call_next(request)
