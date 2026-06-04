"""Run Redis-backed gauge refresh before /metrics is rendered."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from agent_factory.infra.prometheus_gauge_refresh import refresh_prometheus_gauges


class PrometheusGaugeRefreshMiddleware(BaseHTTPMiddleware):
    """Update af_* gauges so prometheus_client export includes live Redis state."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path == "/metrics":
            await refresh_prometheus_gauges()
        return await call_next(request)
