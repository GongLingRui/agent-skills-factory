"""Shared Prometheus registry for HTTP metrics + custom gauges (docs/32)."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge

# Same registry as Instrumentator so /metrics exposes HTTP + custom metrics.
METRICS_REGISTRY = CollectorRegistry()

AF_DOC_PARSE_STREAM_MESSAGES = Gauge(
    "af_doc_parse_stream_messages",
    "Redis Stream mq:doc_jobs length (XLEN).",
    registry=METRICS_REGISTRY,
)

AF_DEGRADATION_LEVEL = Gauge(
    "af_degradation_level",
    "Global degradation level 0..5.",
    registry=METRICS_REGISTRY,
)

AF_MODEL_QUEUE_LENGTH = Gauge(
    "af_model_queue_length",
    "Model request ZSET depth per concurrency class.",
    labelnames=("concurrency_class",),
    registry=METRICS_REGISTRY,
)

AF_MODEL_INFLIGHT = Gauge(
    "af_model_inflight",
    "Inflight model requests per concurrency class.",
    labelnames=("concurrency_class",),
    registry=METRICS_REGISTRY,
)

AF_FRONTEND_EVENTS_TOTAL = Counter(
    "af_frontend_events_total",
    "Browser beacon events from POST /metrics/frontend (docs/32).",
    labelnames=("event_type", "agent_id"),
    registry=METRICS_REGISTRY,
)
