"""Redis-backed temporary Agent disable (docs/19)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

DISABLE_KEY = "agent:disable:{agent_id}"


async def is_agent_disabled(redis: Redis, agent_id: str) -> tuple[bool, str | None]:
    key = DISABLE_KEY.format(agent_id=agent_id)
    raw = await redis.get(key)
    if not raw:
        return False, None
    if isinstance(raw, bytes):
        return True, raw.decode("utf-8", errors="replace")
    return True, str(raw)


async def set_agent_disabled(
    redis: Redis,
    *,
    agent_id: str,
    reason: str,
    duration_minutes: int,
) -> datetime:
    ttl = max(60, duration_minutes * 60)
    key = DISABLE_KEY.format(agent_id=agent_id)
    await redis.setex(key, ttl, reason[:512])
    return datetime.now(UTC) + timedelta(minutes=duration_minutes)
