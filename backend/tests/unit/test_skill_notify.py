"""Redis notify on Skill Registry writes (infra/skill_notify)."""

from __future__ import annotations

import pytest

from agent_factory.infra.skill_notify import (
    SKILL_UPDATED_CHANNEL,
    publish_skill_changed,
)


@pytest.mark.asyncio
async def test_publish_skill_changed_calls_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    class _FakeRedis:
        async def publish(self, channel: str, payload: str) -> int:
            calls.append((channel, payload))
            return 1

    monkeypatch.setattr(
        "agent_factory.infra.skill_notify.get_redis",
        lambda: _FakeRedis(),
    )

    await publish_skill_changed(skill_id="s1", version="1.0.0", action="updated")
    assert len(calls) == 1
    assert calls[0][0] == SKILL_UPDATED_CHANNEL
    assert "s1" in calls[0][1] and "updated" in calls[0][1]
