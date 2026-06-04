"""Optional OpenTelemetry HTTP tracing export (docs/32)."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from agent_factory import __version__

logger = logging.getLogger(__name__)


def setup_opentelemetry(app: FastAPI) -> None:
    """Install OTLP trace export + FastAPI instrumentation when enabled.

    Requires optional dependencies::

        uv sync --extra observability

    """
    from agent_factory.config import get_settings

    s = get_settings()
    if not s.OTEL_ENABLED:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError:
        logger.warning(
            "OTEL_ENABLED=true but OpenTelemetry packages are missing; "
            "install optional extras: uv sync --extra observability"
        )
        return

    if not s.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT.strip():
        logger.warning(
            "OTEL_ENABLED=true but OTEL_EXPORTER_OTLP_TRACES_ENDPOINT is "
            "empty; skipping trace export setup"
        )
        return

    resource = Resource.create(
        {
            "service.name": s.OTEL_SERVICE_NAME,
            "service.version": __version__,
        }
    )
    sampler = TraceIdRatioBased(s.OTEL_TRACES_SAMPLER_RATIO)
    provider = TracerProvider(resource=resource, sampler=sampler)
    exporter = OTLPSpanExporter(endpoint=s.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT.strip())
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
