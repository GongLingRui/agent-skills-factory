"""Request logging with trace_id and URL token masking."""

import logging
import re
import time
import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("agent_factory.access")

_TOKEN_QUERY_RE = re.compile(
    r"([?&]token=)([^&]*)",
    flags=re.IGNORECASE,
)


def _mask_url(url: str) -> str:
    return _TOKEN_QUERY_RE.sub(r"\1[MASKED]", url)


class TraceAndAccessLogMiddleware(BaseHTTPMiddleware):
    """Assign trace_id; log method, masked path, status, duration."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        trace_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:16]}"
        request.state.trace_id = trace_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "request_failed",
                extra={
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": _mask_url(str(request.url)),
                    "duration_ms": duration_ms,
                },
            )
            raise
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "request_completed",
            extra={
                "trace_id": trace_id,
                "method": request.method,
                "path": _mask_url(str(request.url)),
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-ID"] = trace_id
        return response
