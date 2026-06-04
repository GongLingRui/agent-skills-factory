"""Tests for PRD §9.3 degradation matrix."""

from __future__ import annotations

from types import SimpleNamespace

from agent_factory.services.degradation_matrix import (
    DegradationSignals,
    merge_degradation_knobs,
)


def _settings():
    return SimpleNamespace(
        DEGRADATION_KB_TOP_K_REDUCED=5,
        DEGRADATION_CHAT_SMALL_MODEL="small-model",
        DEGRADATION_MAX_TURNS_ON_ERROR_ESCALATION=3,
        DEGRADATION_AUTO_LATENCY_ESCALATE_MS=30_000.0,
        DEGRADATION_LATENCY_REDUCE_TOPK_MS=60_000.0,
        DEGRADATION_LATENCY_SMALL_MODEL_MS=120_000.0,
        DEGRADATION_AUTO_ESCALATE_ERROR_RATE=0.05,
        DOC_PARSE_QUEUE_FORCE_ASYNC_DEPTH=100,
    )


def test_global_level_3_actions():
    knobs = merge_degradation_knobs(
        DegradationSignals(global_level=3),
        _settings(),
    )
    assert knobs.skip_rerank is True
    assert knobs.kb_top_k == 5
    assert knobs.model_override == "small-model"


def test_prd_p99_triggers_skip_rerank():
    knobs = merge_degradation_knobs(
        DegradationSignals(latency_p99_ms=35_000.0),
        _settings(),
    )
    assert knobs.skip_rerank is True


def test_circuit_opens_strip_tools():
    knobs = merge_degradation_knobs(
        DegradationSignals(http_circuit_open=True),
        _settings(),
    )
    assert knobs.strip_nonessential_tools is True
