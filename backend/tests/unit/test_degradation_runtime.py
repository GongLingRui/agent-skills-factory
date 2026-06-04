"""Degradation per-request knobs (prd §9.5)."""

from types import SimpleNamespace

import pytest

from agent_factory.services.degradation_runtime import build_degradation_run_knobs


@pytest.fixture
def settings_like() -> SimpleNamespace:
    return SimpleNamespace(
        DEGRADATION_AUTO_LATENCY_ESCALATE_MS=30_000.0,
        DEGRADATION_LATENCY_REDUCE_TOPK_MS=60_000.0,
        DEGRADATION_LATENCY_SMALL_MODEL_MS=120_000.0,
        DEGRADATION_AUTO_ESCALATE_ERROR_RATE=0.05,
        DEGRADATION_KB_TOP_K_REDUCED=5,
        DEGRADATION_MAX_TURNS_ON_ERROR_ESCALATION=3,
        DEGRADATION_CHAT_SMALL_MODEL="small-chat",
    )


def test_knobs_skip_rerank_only_above_30s(settings_like: SimpleNamespace) -> None:
    k = build_degradation_run_knobs(
        latency_ema_ms=31_000.0,
        error_rate=0.0,
        settings=settings_like,
    )
    assert k.skip_rerank is True
    assert k.kb_top_k is None
    assert k.model_override is None


def test_knobs_reduce_top_k_above_60s(settings_like: SimpleNamespace) -> None:
    k = build_degradation_run_knobs(
        latency_ema_ms=61_000.0,
        error_rate=0.0,
        settings=settings_like,
    )
    assert k.skip_rerank is True
    assert k.kb_top_k == 5


def test_knobs_small_model_above_120s_when_configured(
    settings_like: SimpleNamespace,
) -> None:
    k = build_degradation_run_knobs(
        latency_ema_ms=121_000.0,
        error_rate=0.0,
        settings=settings_like,
    )
    assert k.model_override == "small-chat"


def test_knobs_max_turns_on_high_error(settings_like: SimpleNamespace) -> None:
    k = build_degradation_run_knobs(
        latency_ema_ms=None,
        error_rate=0.06,
        settings=settings_like,
    )
    assert k.max_turns_cap == 3
