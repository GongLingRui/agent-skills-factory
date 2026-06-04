"""PRD §9.3–§9.5 degradation action matrix (docs/13)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_factory.services.degradation_runtime import DegradationRunKnobs

if TYPE_CHECKING:
    from agent_factory.config import Settings


@dataclass(frozen=True)
class DegradationSignals:
    global_level: int = 0
    latency_ema_ms: float | None = None
    latency_p99_ms: float | None = None
    error_rate: float = 0.0
    doc_queue_depth: int = 0
    http_circuit_open: bool = False
    queue_priority: int | None = None


def knobs_from_global_level(level: int, settings: Settings) -> DegradationRunKnobs:
    """Map coarse Redis level 0–5 to ordered §9.3 actions."""
    skip = level >= 1
    top_k = settings.DEGRADATION_KB_TOP_K_REDUCED if level >= 2 else None
    model_ov: str | None = None
    if level >= 3:
        sm = (settings.DEGRADATION_CHAT_SMALL_MODEL or "").strip()
        if sm:
            model_ov = sm
    mcap = settings.DEGRADATION_MAX_TURNS_ON_ERROR_ESCALATION if level >= 3 else None
    strip_tools = level >= 4
    force_async = level >= 2
    return DegradationRunKnobs(
        skip_rerank=skip,
        kb_top_k=top_k,
        model_override=model_ov,
        max_turns_cap=mcap,
        strip_nonessential_tools=strip_tools,
        force_async_documents=force_async,
    )


def knobs_from_prd_signals(signals: DegradationSignals, settings: Settings) -> DegradationRunKnobs:
    """Apply PRD §9.5 trigger table on live signals."""
    skip = False
    top_k: int | None = None
    model_ov: str | None = None
    mcap: int | None = None
    strip = False
    force_async = False

    p99 = signals.latency_p99_ms
    if p99 is None:
        p99 = signals.latency_ema_ms
    if p99 is not None:
        lat = float(p99)
        if lat > settings.DEGRADATION_AUTO_LATENCY_ESCALATE_MS:
            skip = True
        if lat > settings.DEGRADATION_LATENCY_REDUCE_TOPK_MS:
            top_k = settings.DEGRADATION_KB_TOP_K_REDUCED
        if lat > settings.DEGRADATION_LATENCY_SMALL_MODEL_MS:
            sm = (settings.DEGRADATION_CHAT_SMALL_MODEL or "").strip()
            if sm:
                model_ov = sm

    if signals.error_rate >= settings.DEGRADATION_AUTO_ESCALATE_ERROR_RATE:
        mcap = settings.DEGRADATION_MAX_TURNS_ON_ERROR_ESCALATION

    if signals.http_circuit_open:
        strip = True

    doc_depth_thr = int(
        getattr(settings, "DOC_PARSE_QUEUE_FORCE_ASYNC_DEPTH", 100)
    )
    if signals.doc_queue_depth >= doc_depth_thr:
        force_async = True

    qp = signals.queue_priority
    if (
        qp is not None
        and qp >= 9
        and skip
        and p99 is not None
        and float(p99)
        < float(settings.DEGRADATION_AUTO_LATENCY_ESCALATE_MS) * 1.25
    ):
        skip = False

    return DegradationRunKnobs(
        skip_rerank=skip,
        kb_top_k=top_k,
        model_override=model_ov,
        max_turns_cap=mcap,
        strip_nonessential_tools=strip,
        force_async_documents=force_async,
    )


def merge_degradation_knobs(
    signals: DegradationSignals,
    settings: Settings,
) -> DegradationRunKnobs:
    """Combine global level + signal table (stricter wins per field)."""
    a = knobs_from_global_level(signals.global_level, settings)
    b = knobs_from_prd_signals(signals, settings)
    top_k = b.kb_top_k if b.kb_top_k is not None else a.kb_top_k
    if a.kb_top_k is not None and b.kb_top_k is not None:
        top_k = min(a.kb_top_k, b.kb_top_k)
    mcap = a.max_turns_cap
    if b.max_turns_cap is not None:
        mcap = min(mcap, b.max_turns_cap) if mcap is not None else b.max_turns_cap
    return DegradationRunKnobs(
        skip_rerank=a.skip_rerank or b.skip_rerank,
        kb_top_k=top_k,
        model_override=b.model_override or a.model_override,
        max_turns_cap=mcap,
        strip_nonessential_tools=a.strip_nonessential_tools or b.strip_nonessential_tools,
        force_async_documents=a.force_async_documents or b.force_async_documents,
    )
