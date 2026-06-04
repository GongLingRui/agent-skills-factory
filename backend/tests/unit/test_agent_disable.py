"""Tests for Redis-backed agent disable."""

from __future__ import annotations

import pytest

from agent_factory.services.agent_disable import (
    DISABLE_KEY,
    is_agent_disabled,
    set_agent_disabled,
)


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, int | None]] = {}

    async def get(self, key: str) -> str | None:
        val, _ = self._store.get(key, (None, None))
        return val

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        self._store[key] = (value, seconds)
        return True


@pytest.mark.asyncio
async def test_not_disabled():
    redis = _FakeRedis()
    disabled, reason = await is_agent_disabled(redis, "agent-a")
    assert disabled is False
    assert reason is None


@pytest.mark.asyncio
async def test_set_and_check():
    redis = _FakeRedis()
    exp = await set_agent_disabled(redis, agent_id="agent-a", reason="test", duration_minutes=10)
    assert exp is not None
    disabled, reason = await is_agent_disabled(redis, "agent-a")
    assert disabled is True
    assert reason == "test"


@pytest.mark.asyncio
async def test_key_format():
    redis = _FakeRedis()
    await set_agent_disabled(redis, agent_id="x-1", reason="r", duration_minutes=1)
    key = DISABLE_KEY.format(agent_id="x-1")
    assert key == "agent:disable:x-1"
    assert key in redis._store
