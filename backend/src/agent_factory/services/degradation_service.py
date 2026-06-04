"""Global degradation level management (docs/13, docs/34)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agent_factory.infra.redis import get_redis

logger = logging.getLogger(__name__)

REDIS_KEY = "global:degradation:level"
REDIS_REASON_KEY = "global:degradation:reason"
OPERATOR_HOLD_KEY = "global:degradation:operator_hold"
GOOD_STREAK_KEY = "global:degradation:good_streak_since"

# 6-level degradation (0=normal, 5=max)
LEVEL_DESCRIPTIONS: dict[int, str] = {
    0: "normal",
    1: "mild: reduce non-essential features",
    2: "moderate: throttle batch tasks",
    3: "significant: disable file uploads",
    4: "severe: interactive only, no tools",
    5: "critical: read-only mode",
}

# Short hints for Chat Widget (prd.md §9.5).
LEVEL_WIDGET_HINTS: dict[int, str] = {
    0: "",
    1: "系统繁忙，已启用快速模式。",
    2: "系统繁忙，批量任务可能排队更久。",
    3: "系统繁忙，文件上传可能受限。",
    4: "系统繁忙，当前为对话模式（工具暂时关闭）。",
    5: "系统只读维护中，请稍后再试。",
}


def widget_degradation_hint(level: int, reason: str) -> str:
    """Human-readable banner text for level + optional ops reason."""
    base = (LEVEL_WIDGET_HINTS.get(level) or "").strip()
    r = (reason or "").strip()
    if base and r:
        return f"{base}（{r}）"
    return base or r


@dataclass
class DegradationState:
    level: int
    reason: str


class DegradationService:
    """Read/write global degradation state from Redis."""

    async def get_level(self) -> DegradationState:
        try:
            redis = get_redis()
            raw = await redis.get(REDIS_KEY)
            reason = await redis.get(REDIS_REASON_KEY) or ""
            level = int(raw) if raw else 0
            return DegradationState(level=level, reason=reason)
        except Exception:
            logger.exception("Failed to read degradation level")
            return DegradationState(level=0, reason="")

    async def set_level(
        self,
        level: int,
        reason: str,
        *,
        from_operator: bool = False,
    ) -> None:
        if level < 0 or level > 5:
            raise ValueError("Degradation level must be 0-5")
        try:
            redis = get_redis()
            await redis.set(REDIS_KEY, str(level))
            await redis.set(REDIS_REASON_KEY, reason)
            if from_operator:
                if level > 0:
                    await redis.set(OPERATOR_HOLD_KEY, "1")
                else:
                    await redis.delete(OPERATOR_HOLD_KEY)
            logger.warning(
                "Degradation level set to %d: %s (operator=%s)",
                level,
                reason,
                from_operator,
            )
        except Exception:
            logger.exception("Failed to set degradation level")
