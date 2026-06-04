"""FastAPI application entrypoint."""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from agent_factory import __version__
from agent_factory.api.health import router as health_router
from agent_factory.api.v1.router import api_v1_router
from agent_factory.config import get_settings
from agent_factory.infra.db import dispose_engine
from agent_factory.infra.otel import setup_opentelemetry
from agent_factory.infra.prometheus_registry import METRICS_REGISTRY
from agent_factory.infra.redis import close_redis
from agent_factory.middleware.error_handler import (
    AgentFactoryException,
    agent_factory_exception_handler,
    generic_exception_handler,
)
from agent_factory.middleware.logging_mw import TraceAndAccessLogMiddleware
from agent_factory.middleware.prometheus_gauge_refresh import (
    PrometheusGaugeRefreshMiddleware,
)
from agent_factory.middleware.rate_limit import RateLimitMiddleware
from agent_factory.middleware.security_headers import SecurityHeadersMiddleware
from agent_factory.services.feishu_transport import (
    start_feishu_transport,
    stop_feishu_transport,
)
from agent_factory.services.startup_checks import log_startup_dependency_status

logger = logging.getLogger(__name__)


async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Do not expose field paths/messages to clients in production (信息安全 §6.2)."""
    rid = getattr(request.state, "trace_id", None) or str(uuid.uuid4())
    logger.info(
        "request_validation_failed",
        extra={"request_id": rid, "errors": exc.errors()},
    )
    s = get_settings()
    err: dict = {
        "code": "VALIDATION_ERROR",
        "message": "Invalid request",
        "request_id": rid,
    }
    if s.APP_ENV == "development":
        err["details"] = exc.errors()
    return JSONResponse(status_code=422, content={"error": err})


def _configure_logging() -> None:
    s = get_settings()
    logging.basicConfig(
        level=getattr(logging, s.LOG_LEVEL.upper(), logging.INFO),
        format="%(message)s",
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configure_logging()
    s = get_settings()
    await log_startup_dependency_status(s)
    await start_feishu_transport()
    yield
    await stop_feishu_transport()
    await dispose_engine()
    await close_redis()


def create_app(*, enable_prometheus: bool = True) -> FastAPI:
    """Build FastAPI application.

    Args:
        enable_prometheus: When False, skip HTTP metrics registration (avoids
            duplicate CollectorRegistry errors when tests create multiple apps).
    """
    s = get_settings()
    app = FastAPI(
        title="Agent App Factory",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if s.APP_ENV != "production" else None,
        redoc_url="/redoc" if s.APP_ENV != "production" else None,
    )

    app.add_exception_handler(AgentFactoryException, agent_factory_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    app.add_middleware(TraceAndAccessLogMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(api_v1_router, prefix="/api/v1")

    if enable_prometheus:
        app.add_middleware(PrometheusGaugeRefreshMiddleware)
        instrumentator = Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            should_respect_env_var=False,
            should_instrument_requests_inprogress=True,
            excluded_handlers=[
                "/health",
                "/ready",
                "/metrics",
            ],
            registry=METRICS_REGISTRY,
        )
        instrumentator.instrument(app, metric_namespace="af").expose(
            app,
            endpoint="/metrics",
            include_in_schema=False,
        )

    setup_opentelemetry(app)

    return app


app = create_app()
