"""HTTP Tool Gateway circuit breaker (Redis; docs/09, plan §12)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

from agent_factory.config.settings import Settings
from agent_factory.middleware.error_handler import AgentFactoryException

logger = logging.getLogger(__name__)

OPEN_KEY = "cb:httptool:{scope}:open"
FAIL_KEY = "cb:httptool:{scope}:fail"


@dataclass(frozen=True)
class HttpToolCircuitConfig:
    """Effective breaker parameters after merging Settings + Tool row."""

    enabled: bool
    failure_threshold: int
    window_seconds: int
    open_seconds: int


def http_tool_circuit_scope(
    tool_id: str,
    department: str | None,
    *,
    per_department: bool,
) -> str:
    """Redis key segment (ASCII-safe)."""
    if per_department and department:
        return f"{tool_id}:d:{department}"
    return tool_id


def build_http_tool_circuit_config(
    settings: Settings,
    rate_limit: dict[str, Any] | None,
) -> HttpToolCircuitConfig:
    """Merge env defaults with optional ``tools.rate_limit`` JSON."""
    base_enabled = settings.TOOL_HTTP_CIRCUIT_ENABLED
    thr = settings.TOOL_HTTP_CIRCUIT_FAILURE_THRESHOLD
    win = settings.TOOL_HTTP_CIRCUIT_WINDOW_SECONDS
    opn = settings.TOOL_HTTP_CIRCUIT_OPEN_SECONDS

    cb: dict[str, Any] = {}
    if isinstance(rate_limit, dict):
        raw = rate_limit.get("circuit_breaker")
        if isinstance(raw, dict):
            cb = raw

    if "enabled" in cb:
        base_enabled = base_enabled and bool(cb["enabled"])
    if "failure_threshold" in cb:
        thr = int(cb["failure_threshold"])
    if "window_seconds" in cb:
        win = int(cb["window_seconds"])
    if "open_seconds" in cb:
        opn = int(cb["open_seconds"])

    return HttpToolCircuitConfig(
        enabled=base_enabled and thr > 0,
        failure_threshold=max(0, thr),
        window_seconds=max(1, win),
        open_seconds=max(1, opn),
    )


async def assert_http_tool_circuit_closed(
    redis: Redis,
    scope: str,
    cfg: HttpToolCircuitConfig,
) -> None:
    if not cfg.enabled:
        return
    key = OPEN_KEY.format(scope=scope)
    if await redis.get(key):
        raise AgentFactoryException(
            "TOOL_CIRCUIT_OPEN",
            "工具暂时不可用（熔断中），请稍后重试",
            status_code=503,
        )


async def record_http_tool_failure(
    redis: Redis,
    scope: str,
    cfg: HttpToolCircuitConfig,
) -> None:
    if not cfg.enabled:
        return
    fk = FAIL_KEY.format(scope=scope)
    n = await redis.incr(fk)
    if n == 1:
        await redis.expire(fk, cfg.window_seconds)
    if n >= cfg.failure_threshold:
        ok = OPEN_KEY.format(scope=scope)
        await redis.set(ok, "1", ex=cfg.open_seconds)
        await redis.delete(fk)
        logger.warning(
            "HTTP tool circuit opened: scope=%s failures=%s",
            scope,
            n,
        )


async def clear_http_tool_failures(redis: Redis, scope: str) -> None:
    await redis.delete(FAIL_KEY.format(scope=scope))


def failure_counts_toward_circuit(exc: AgentFactoryException) -> bool:
    """Trip breaker on transport / upstream 5xx only."""
    return exc.code in frozenset(
        {
            "TOOL_HTTP_TRANSPORT",
            "TOOL_HTTP_UPSTREAM",
        }
    )


async def any_http_tool_circuit_open(redis: Redis) -> bool:
    """True if at least one ``cb:httptool:*:open`` key exists (prd §9.5)."""
    try:
        async for _ in redis.scan_iter(match="cb:httptool:*:open", count=64):
            return True
    except Exception:
        logger.exception("any_http_tool_circuit_open scan failed")
    return False
