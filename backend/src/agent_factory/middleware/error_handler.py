"""Global exception handlers (structured errors, trace_id)."""

import logging
import uuid
from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AgentFactoryException(Exception):
    """Business-level error with HTTP mapping."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def agent_factory_exception_handler(
    request: Request,
    exc: AgentFactoryException,
) -> JSONResponse:
    rid = getattr(request.state, "trace_id", None) or str(uuid.uuid4())
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": rid,
            }
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = getattr(request.state, "trace_id", None) or str(uuid.uuid4())
    from agent_factory.config import get_settings
    from agent_factory.services.startup_checks import (
        dependency_unavailable_message,
        is_connection_refused_error,
    )

    if is_connection_refused_error(exc):
        settings = get_settings()
        logger.error(
            "dependency_connection_refused",
            extra={"request_id": rid, "path": request.url.path},
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "DEPENDENCY_UNAVAILABLE",
                    "message": dependency_unavailable_message(settings),
                    "request_id": rid,
                }
            },
        )

    logger.exception(
        "Unhandled exception",
        extra={"request_id": rid},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
                "request_id": rid,
            }
        },
    )


def error_body(code: str, message: str, request_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "request_id": request_id}}
