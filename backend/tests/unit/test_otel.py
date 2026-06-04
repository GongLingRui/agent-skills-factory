"""Optional OpenTelemetry bootstrap."""

from fastapi import FastAPI


def test_setup_opentelemetry_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "false")
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    from agent_factory.infra.otel import setup_opentelemetry

    setup_opentelemetry(FastAPI())
    get_settings.cache_clear()
