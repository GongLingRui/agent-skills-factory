"""Tests for degradation service."""

import pytest

from agent_factory.services.degradation_service import DegradationService


class _MemoryRedis:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        v = self._d.get(key)
        return v if v is not None else None

    async def set(self, key: str, value: str) -> bool:
        self._d[key] = value
        return True


@pytest.mark.asyncio
async def test_get_level_default(monkeypatch):
    """Isolated from real Redis (integration tests may set global level)."""
    mem = _MemoryRedis()
    monkeypatch.setattr(
        "agent_factory.services.degradation_service.get_redis",
        lambda: mem,
    )
    svc = DegradationService()
    state = await svc.get_level()
    assert state.level == 0
    assert state.reason == ""


@pytest.mark.asyncio
async def test_set_level_invalid():
    svc = DegradationService()
    with pytest.raises(ValueError):
        await svc.set_level(10, "too high")
