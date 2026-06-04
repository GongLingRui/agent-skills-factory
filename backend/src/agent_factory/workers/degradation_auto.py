"""Auto escalation / step-down for global degradation (docs/13 §自动恢复)."""

from __future__ import annotations

import logging
import time

from agent_factory.config import get_settings
from agent_factory.infra.doc_queue import doc_parse_queue_depth
from agent_factory.infra.model_runtime_signals import (
    read_latency_ema_ms,
    window_error_rate,
)
from agent_factory.infra.redis import get_redis
from agent_factory.infra.tool_circuit_breaker import any_http_tool_circuit_open
from agent_factory.services.degradation_service import (
    GOOD_STREAK_KEY,
    OPERATOR_HOLD_KEY,
    DegradationService,
)

logger = logging.getLogger(__name__)


def _latency_floor_level(lat: float | None, settings: object) -> int:
    """Minimum coarse level implied by latency EMA (prd §9.5 tiers)."""
    if lat is None:
        return 0
    thr_small = float(
        getattr(settings, "DEGRADATION_LATENCY_SMALL_MODEL_MS", 120_000.0)
    )
    thr_topk = float(
        getattr(settings, "DEGRADATION_LATENCY_REDUCE_TOPK_MS", 60_000.0)
    )
    thr_first = float(
        getattr(settings, "DEGRADATION_AUTO_LATENCY_ESCALATE_MS", 30_000.0)
    )
    if lat >= thr_small:
        return 3
    if lat >= thr_topk:
        return 2
    if lat >= thr_first:
        return 1
    return 0


async def run_degradation_auto_tick() -> None:
    """Cron hook: adjust degradation level from Redis model signals."""
    settings = get_settings()
    if not settings.DEGRADATION_AUTO_ENABLED:
        return
    redis = get_redis()
    if await redis.get(OPERATOR_HOLD_KEY):
        return
    svc = DegradationService()
    state = await svc.get_level()
    win = settings.DEGRADATION_AUTO_WINDOW_MINUTES
    rate, _fails, atts = await window_error_rate(window_minutes=win, redis=redis)
    lat = await read_latency_ema_ms(redis)
    lat_floor = _latency_floor_level(lat, settings)
    bad_lat = lat_floor > 0
    bad_rate = rate >= settings.DEGRADATION_AUTO_ESCALATE_ERROR_RATE
    doc_depth = await doc_parse_queue_depth(redis)
    doc_bad = doc_depth >= settings.DOC_PARSE_QUEUE_FORCE_ASYNC_DEPTH
    circ_bad = await any_http_tool_circuit_open(redis)
    stress_floor = max(
        lat_floor,
        (1 if doc_bad else 0),
        (1 if circ_bad else 0),
    )
    if state.level < 5 and (bad_rate or bad_lat or doc_bad or circ_bad):
        nxt = min(5, max(state.level + 1, stress_floor))
        await svc.set_level(
            nxt,
            (
                f"auto:rate={rate:.3f} att={atts} lat={lat} "
                f"docq={doc_depth} circ={int(circ_bad)}"
            ),
            from_operator=False,
        )
        await redis.delete(GOOD_STREAK_KEY)
        logger.warning(
            "Degradation auto-escalate -> %s (rate=%.3f att=%s)",
            nxt,
            rate,
            atts,
        )
        return
    cool_lat = lat is None or lat < settings.DEGRADATION_AUTO_LATENCY_RECOVER_MS
    low_rate = rate <= settings.DEGRADATION_AUTO_RECOVER_MAX_ERROR_RATE
    min_att = settings.DEGRADATION_AUTO_MIN_ATTEMPTS_FOR_RECOVER
    if (
        state.level > 0
        and low_rate
        and cool_lat
        and atts >= min_att
    ):
        raw = await redis.get(GOOD_STREAK_KEY)
        now = time.time()
        if raw is None:
            await redis.set(GOOD_STREAK_KEY, str(int(now)))
            await redis.expire(
                GOOD_STREAK_KEY,
                settings.DEGRADATION_AUTO_GOOD_STREAK_SECONDS * 2,
            )
        elif now - float(raw) >= settings.DEGRADATION_AUTO_GOOD_STREAK_SECONDS:
            await svc.set_level(
                state.level - 1,
                "auto:metrics_normalized",
                from_operator=False,
            )
            await redis.delete(GOOD_STREAK_KEY)
            logger.info("Degradation auto step-down -> %s", state.level - 1)
    else:
        await redis.delete(GOOD_STREAK_KEY)
