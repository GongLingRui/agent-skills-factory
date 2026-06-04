"""Lightweight Redis signals for degradation auto logic (docs/13 §自动恢复)."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from agent_factory.infra.redis import get_redis

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_SIGNAL_TTL = 180


def _minute_bucket(ts: float | None = None) -> int:
    return int((ts or time.time()) // 60)


async def record_model_attempt(redis: Redis | None = None) -> None:
    r = redis or get_redis()
    b = _minute_bucket()
    k = f"mw:att:{b}"
    try:
        await r.incr(k)
        await r.expire(k, _SIGNAL_TTL)
    except Exception:
        logger.exception("record_model_attempt failed")


async def record_model_failure(redis: Redis | None = None) -> None:
    r = redis or get_redis()
    b = _minute_bucket()
    k = f"mw:fail:{b}"
    try:
        await r.incr(k)
        await r.expire(k, _SIGNAL_TTL)
    except Exception:
        logger.exception("record_model_failure failed")


async def record_model_success_ms(
    latency_ms: float,
    redis: Redis | None = None,
) -> None:
    r = redis or get_redis()
    try:
        raw = await r.get("mw:lat_ema_ms")
        prev = float(raw) if raw is not None else latency_ms
        ema = 0.85 * prev + 0.15 * max(latency_ms, 0.0)
        await r.set("mw:lat_ema_ms", f"{ema:.1f}")
    except Exception:
        logger.exception("record_model_success_ms failed")


async def window_error_rate(
    *,
    window_minutes: int,
    redis: Redis | None = None,
) -> tuple[float, int, int]:
    """Return (fail_rate, total_fails, total_attempts) over last N minute buckets."""
    r = redis or get_redis()
    now = time.time()
    fails = 0
    atts = 0
    try:
        for i in range(window_minutes):
            b = _minute_bucket(now) - i
            fk = f"mw:fail:{b}"
            ak = f"mw:att:{b}"
            fv = await r.get(fk)
            av = await r.get(ak)
            fails += int(fv) if fv is not None else 0
            atts += int(av) if av is not None else 0
    except Exception:
        logger.exception("window_error_rate failed")
        return 0.0, 0, 0
    rate = (fails / atts) if atts > 0 else 0.0
    return rate, fails, atts


async def read_latency_ema_ms(redis: Redis | None = None) -> float | None:
    r = redis or get_redis()
    try:
        raw = await r.get("mw:lat_ema_ms")
        if raw is None:
            return None
        return float(raw)
    except Exception:
        return None


async def record_model_latency_sample(
    latency_ms: float,
    redis: Redis | None = None,
) -> None:
    """Append sample for P99 window (prd §9.5)."""
    r = redis or get_redis()
    b = _minute_bucket()
    key = f"mw:lat_samples:{b}"
    try:
        await r.lpush(key, f"{max(latency_ms, 0.0):.2f}")
        await r.ltrim(key, 0, 499)
        await r.expire(key, _SIGNAL_TTL)
    except Exception:
        logger.exception("record_model_latency_sample failed")


async def read_latency_p99_ms(
    *,
    window_minutes: int = 5,
    redis: Redis | None = None,
) -> float | None:
    """Approximate P99 from recent minute buckets."""
    r = redis or get_redis()
    now = time.time()
    samples: list[float] = []
    try:
        for i in range(window_minutes):
            b = _minute_bucket(now) - i
            key = f"mw:lat_samples:{b}"
            rows = await r.lrange(key, 0, -1)
            for row in rows:
                try:
                    samples.append(float(row))
                except (TypeError, ValueError):
                    continue
    except Exception:
        logger.exception("read_latency_p99_ms failed")
        return None
    if not samples:
        return None
    samples.sort()
    idx = int(0.99 * (len(samples) - 1))
    return samples[max(0, idx)]
