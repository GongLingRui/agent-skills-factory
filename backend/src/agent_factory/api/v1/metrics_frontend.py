"""POST /metrics/frontend for browser beacon data (docs/32)."""

import logging
import re
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from agent_factory.infra.prometheus_registry import AF_FRONTEND_EVENTS_TOTAL

router = APIRouter()
logger = logging.getLogger("frontend.metrics")

_LABEL_SAFE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _sanitize_prometheus_label(value: str, *, max_len: int = 64) -> str:
    """Keep label cardinality bounded and Prometheus-safe."""
    raw = value.strip()[:max_len]
    if not raw:
        return "_"
    cleaned = _LABEL_SAFE.sub("_", raw)
    return cleaned if cleaned else "_"


class FrontendMetric(BaseModel):
    agent_id: str | None = Field(None, max_length=64)
    event_type: str = Field(..., max_length=32)
    duration_ms: int | None = None
    payload: dict[str, Any] | None = None


@router.post("/metrics/frontend")
async def post_frontend_metrics(
    body: FrontendMetric,
    request: Request,
) -> dict[str, str]:
    """Receive frontend performance / error metrics via navigator.sendBeacon.

    Increments ``af_frontend_events_total`` for Grafana (prd §10.6 Agent 层观测).
    """
    client_ip = request.client.host if request.client else "unknown"
    logger.info(
        "frontend_metric agent=%s type=%s ip=%s duration=%s",
        body.agent_id,
        body.event_type,
        client_ip,
        body.duration_ms,
    )
    agent_l = _sanitize_prometheus_label(body.agent_id or "")
    et = _sanitize_prometheus_label(body.event_type, max_len=32)
    AF_FRONTEND_EVENTS_TOTAL.labels(
        event_type=et,
        agent_id=agent_l,
    ).inc()
    return {"status": "accepted"}
