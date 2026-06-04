"""Shared async Redis client."""

from redis.asyncio import Redis

from agent_factory.config import get_settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        s = get_settings()
        _redis = Redis.from_url(
            s.REDIS_URL,
            max_connections=s.REDIS_POOL_SIZE,
            decode_responses=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
