"""Refresh custom Prometheus gauges from Redis (plan §13.2 observability gap)."""

from __future__ import annotations

import logging

from agent_factory.infra.doc_queue import STREAM_KEY
from agent_factory.infra.model_queue import QUEUE_CLASSES
from agent_factory.infra.prometheus_registry import (
    AF_DEGRADATION_LEVEL,
    AF_DOC_PARSE_STREAM_MESSAGES,
    AF_MODEL_INFLIGHT,
    AF_MODEL_QUEUE_LENGTH,
)
from agent_factory.infra.redis import get_redis
from agent_factory.services.degradation_service import DegradationService

logger = logging.getLogger(__name__)


async def refresh_prometheus_gauges() -> None:
    """Best-effort snapshot for scrape (must stay lightweight)."""
    redis = get_redis()

    try:
        ln = await redis.xlen(STREAM_KEY)
        AF_DOC_PARSE_STREAM_MESSAGES.set(float(ln))
    except Exception:
        logger.exception("metrics: doc stream xlen failed")
        AF_DOC_PARSE_STREAM_MESSAGES.set(0.0)

    try:
        svc = DegradationService()
        st = await svc.get_level()
        AF_DEGRADATION_LEVEL.set(float(st.level))
    except Exception:
        logger.exception("metrics: degradation level failed")
        AF_DEGRADATION_LEVEL.set(0.0)

    for cls in QUEUE_CLASSES:
        zkey = f"model:zqueue:{cls}"
        ikey = f"model:inflight:{cls}"
        try:
            zc = await redis.zcard(zkey)
            AF_MODEL_QUEUE_LENGTH.labels(concurrency_class=cls).set(float(zc))
        except Exception:
            AF_MODEL_QUEUE_LENGTH.labels(concurrency_class=cls).set(0.0)
        try:
            raw = await redis.get(ikey)
            inf = int(raw) if raw is not None else 0
            AF_MODEL_INFLIGHT.labels(concurrency_class=cls).set(float(inf))
        except Exception:
            AF_MODEL_INFLIGHT.labels(concurrency_class=cls).set(0.0)
