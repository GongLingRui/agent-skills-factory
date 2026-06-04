"""Per-request degradation knobs (prd §9.3, §9.5; docs/13)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, FrozenSet

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config.settings import Settings
from agent_factory.db.models.tool import Tool
from agent_factory.infra.tool_circuit_breaker import any_http_tool_circuit_open

if TYPE_CHECKING:
    from redis.asyncio import Redis

# Built-ins always kept when filtering registry tools under circuit stress.
BUILTIN_TOOL_IDS: FrozenSet[str] = frozenset(
    {"kb.search", "doc.extract", "read_reference", "risk.rule_check"},
)


@dataclass(frozen=True)
class DegradationRunKnobs:
    """Runner + Tool Gateway hints derived from live signals (not Redis level)."""

    skip_rerank: bool = False
    kb_top_k: int | None = None
    model_override: str | None = None
    max_turns_cap: int | None = None
    strip_nonessential_tools: bool = False
    force_async_documents: bool = False


def build_degradation_run_knobs(
    *,
    latency_ema_ms: float | None,
    error_rate: float,
    settings: Settings,
    queue_priority: int | None = None,
    global_level: int = 0,
    latency_p99_ms: float | None = None,
    doc_queue_depth: int = 0,
    http_circuit_open: bool = False,
) -> DegradationRunKnobs:
    """Map PRD §9.3 matrix: global level + live signals."""
    from agent_factory.services.degradation_matrix import (
        DegradationSignals,
        merge_degradation_knobs,
    )

    return merge_degradation_knobs(
        DegradationSignals(
            global_level=global_level,
            latency_ema_ms=latency_ema_ms,
            latency_p99_ms=latency_p99_ms,
            error_rate=error_rate,
            doc_queue_depth=doc_queue_depth,
            http_circuit_open=http_circuit_open,
            queue_priority=queue_priority,
        ),
        settings,
    )


async def filter_allowed_tools_under_circuit(
    db: AsyncSession,
    redis: Redis,
    allowed_tools: list[str],
    *,
    agent_degradation_exempt: bool,
    settings: Settings,
) -> list[str]:
    """Drop registry tools marked non-essential when any HTTP tool circuit is open."""
    if agent_degradation_exempt:
        return list(allowed_tools)
    if not allowed_tools:
        return []
    if not await any_http_tool_circuit_open(redis):
        return list(allowed_tools)

    registry_ids = [t for t in allowed_tools if t not in BUILTIN_TOOL_IDS]
    if not registry_ids:
        return list(allowed_tools)

    q = await db.execute(
        select(Tool.id, Tool.implementation).where(
            Tool.id.in_(registry_ids),
            Tool.status == "active",
        )
    )
    drop: set[str] = set()
    for tid, impl in q.all():
        impl_d = impl if isinstance(impl, dict) else {}
        if bool(impl_d.get("degradation_nonessential")):
            drop.add(str(tid))

    if not drop:
        return list(allowed_tools)
    return [t for t in allowed_tools if t not in drop]
