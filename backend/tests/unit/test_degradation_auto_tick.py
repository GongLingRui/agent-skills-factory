"""Degradation auto tick (docs/13)."""

import pytest

from agent_factory.services.degradation_service import (
    GOOD_STREAK_KEY,
    OPERATOR_HOLD_KEY,
    REDIS_KEY,
    REDIS_REASON_KEY,
    DegradationService,
)
from agent_factory.workers import degradation_auto


class _MemRedis:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    async def xlen(self, _key: str) -> int:
        return 0

    async def scan_iter(self, *_a, **_k):
        for _ in ():
            yield _

    async def get(self, key: str) -> str | None:
        v = self._d.get(key)
        return v if v is not None else None

    async def set(self, key: str, value: str) -> bool:
        self._d[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self._d:
                del self._d[k]
                n += 1
        return n

    async def expire(self, *_a, **_k) -> bool:
        return True


@pytest.mark.asyncio
async def test_degradation_auto_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.get_settings",
        lambda: type(
            "S",
            (),
            {"DEGRADATION_AUTO_ENABLED": False},
        )(),
    )
    called = False

    async def _no(*_a, **_k):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.window_error_rate",
        _no,
    )
    await degradation_auto.run_degradation_auto_tick()
    assert not called


@pytest.mark.asyncio
async def test_degradation_auto_skips_on_operator_hold(monkeypatch):
    mem = _MemRedis()
    mem._d[OPERATOR_HOLD_KEY] = "1"

    class _S:
        DEGRADATION_AUTO_ENABLED = True
        DEGRADATION_AUTO_WINDOW_MINUTES = 3
        DOC_PARSE_QUEUE_FORCE_ASYNC_DEPTH = 100

    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.get_settings",
        lambda: _S(),
    )
    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.get_redis",
        lambda: mem,
    )
    await degradation_auto.run_degradation_auto_tick()


@pytest.mark.asyncio
async def test_operator_hold_set_on_manual_level(monkeypatch):
    mem = _MemRedis()
    monkeypatch.setattr(
        "agent_factory.services.degradation_service.get_redis",
        lambda: mem,
    )
    svc = DegradationService()
    await svc.set_level(2, "ops", from_operator=True)
    assert mem._d.get(REDIS_KEY) == "2"
    assert mem._d.get(OPERATOR_HOLD_KEY) == "1"
    await svc.set_level(0, "", from_operator=True)
    assert mem._d.get(REDIS_KEY) == "0"
    assert OPERATOR_HOLD_KEY not in mem._d


@pytest.mark.asyncio
async def test_auto_escalate_when_high_error_rate(monkeypatch):
    mem = _MemRedis()
    mem._d[REDIS_KEY] = "0"
    mem._d[REDIS_REASON_KEY] = ""

    def _redis() -> _MemRedis:
        return mem

    monkeypatch.setattr(
        "agent_factory.services.degradation_service.get_redis",
        _redis,
    )
    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.get_redis",
        _redis,
    )

    class _S:
        DEGRADATION_AUTO_ENABLED = True
        DEGRADATION_AUTO_WINDOW_MINUTES = 3
        DEGRADATION_AUTO_ESCALATE_ERROR_RATE = 0.1
        DEGRADATION_AUTO_RECOVER_MAX_ERROR_RATE = 0.02
        DEGRADATION_AUTO_GOOD_STREAK_SECONDS = 300
        DEGRADATION_AUTO_LATENCY_ESCALATE_MS = 99_999.0
        DEGRADATION_AUTO_LATENCY_RECOVER_MS = 8000.0
        DEGRADATION_AUTO_MIN_ATTEMPTS_FOR_RECOVER = 1
        DOC_PARSE_QUEUE_FORCE_ASYNC_DEPTH = 100
        DEGRADATION_LATENCY_REDUCE_TOPK_MS = 60_000.0
        DEGRADATION_LATENCY_SMALL_MODEL_MS = 120_000.0

    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.get_settings",
        lambda: _S(),
    )
    async def _fake_window(**_k):
        return (0.5, 5, 20)

    async def _fake_lat(*_a, **_k):
        return None

    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.window_error_rate",
        _fake_window,
    )
    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.read_latency_ema_ms",
        _fake_lat,
    )
    await degradation_auto.run_degradation_auto_tick()
    assert mem._d.get(REDIS_KEY) == "1"
    assert GOOD_STREAK_KEY not in mem._d


@pytest.mark.asyncio
async def test_auto_escalate_when_high_latency(monkeypatch):
    mem = _MemRedis()
    mem._d[REDIS_KEY] = "0"
    mem._d[REDIS_REASON_KEY] = ""

    def _redis() -> _MemRedis:
        return mem

    monkeypatch.setattr(
        "agent_factory.services.degradation_service.get_redis",
        _redis,
    )
    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.get_redis",
        _redis,
    )

    class _S:
        DEGRADATION_AUTO_ENABLED = True
        DEGRADATION_AUTO_WINDOW_MINUTES = 3
        DEGRADATION_AUTO_ESCALATE_ERROR_RATE = 0.99
        DEGRADATION_AUTO_RECOVER_MAX_ERROR_RATE = 0.02
        DEGRADATION_AUTO_GOOD_STREAK_SECONDS = 300
        DEGRADATION_AUTO_LATENCY_ESCALATE_MS = 10_000.0
        DEGRADATION_AUTO_LATENCY_RECOVER_MS = 8000.0
        DEGRADATION_AUTO_MIN_ATTEMPTS_FOR_RECOVER = 1
        DOC_PARSE_QUEUE_FORCE_ASYNC_DEPTH = 100
        DEGRADATION_LATENCY_REDUCE_TOPK_MS = 60_000.0
        DEGRADATION_LATENCY_SMALL_MODEL_MS = 120_000.0

    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.get_settings",
        lambda: _S(),
    )

    async def _fake_window(**_k):
        return (0.01, 1, 20)

    async def _fake_lat(*_a, **_k):
        return 15_000.0

    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.window_error_rate",
        _fake_window,
    )
    monkeypatch.setattr(
        "agent_factory.workers.degradation_auto.read_latency_ema_ms",
        _fake_lat,
    )
    await degradation_auto.run_degradation_auto_tick()
    assert mem._d.get(REDIS_KEY) == "1"
