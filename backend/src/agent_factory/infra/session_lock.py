"""Redis-based session lock to prevent concurrent turns (docs/08).

Fairness: waiters are ordered in a per-session FIFO queue so the first
waiter to enqueue is the first to acquire after the lock is released
(plan §12).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

LOCK_KEY_PREFIX = "lock:session:"
QUEUE_KEY_PREFIX = "queue:session:"
DEFAULT_LOCK_TTL_SECONDS = 60

# Lua: only acquire when no waiters are queued (avoids barging ahead of FIFO).
_ACQUIRE_IF_QUEUE_EMPTY_V1 = """
-- ACQUIRE_IF_QUEUE_EMPTY_V1
if redis.call('LLEN', KEYS[2]) > 0 then
  return 0
end
if redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1]) then
  return 1
end
return 0
"""

_ENQUEUE_WAITER_V1 = """
-- ENQUEUE_WAITER_V1
if redis.call('LLEN', KEYS[1]) >= tonumber(ARGV[1]) then
  return 0
end
redis.call('RPUSH', KEYS[1], ARGV[2])
return 1
"""


async def _eval_try_acquire_if_queue_empty(
    redis: Redis,
    lock_key: str,
    queue_key: str,
    ttl_seconds: int,
) -> int:
    """Return 1 if lock acquired, else 0."""
    raw = await redis.eval(
        _ACQUIRE_IF_QUEUE_EMPTY_V1,
        2,
        lock_key,
        queue_key,
        str(int(ttl_seconds)),
    )
    return int(raw)


async def _eval_enqueue_waiter(
    redis: Redis,
    queue_key: str,
    max_waiters: int,
    token: str,
) -> bool:
    """Atomically enqueue if queue length is below ``max_waiters``."""
    raw = await redis.eval(
        _ENQUEUE_WAITER_V1,
        1,
        queue_key,
        str(int(max_waiters)),
        token,
    )
    return int(raw) == 1


async def acquire_session_lock(
    redis: Redis,
    session_id: str,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
) -> bool:
    """Try to acquire lock only when the wait queue is empty (no barging)."""
    lock_key = f"{LOCK_KEY_PREFIX}{session_id}"
    queue_key = f"{QUEUE_KEY_PREFIX}{session_id}"
    got = await _eval_try_acquire_if_queue_empty(
        redis, lock_key, queue_key, ttl_seconds
    )
    if got == 1:
        logger.debug("Session lock acquired: %s", session_id)
        return True
    logger.warning("Session lock not acquired: %s", session_id)
    return False


async def release_session_lock(redis: Redis, session_id: str) -> None:
    """Release the Redis lock for the session."""
    key = f"{LOCK_KEY_PREFIX}{session_id}"
    await redis.delete(key)
    logger.debug("Session lock released: %s", session_id)


async def acquire_session_lock_or_wait(
    redis: Redis,
    session_id: str,
    *,
    max_waiters: int,
    poll_interval_ms: int,
    max_wait_ms: int,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
) -> tuple[bool, str | None]:
    """Try lock; if busy, enqueue and wait FIFO until lock or timeout.

    Returns ``(True, None)`` when the lock is held by this caller.

    On failure returns ``(False, code)``:

    - ``SESSION_BUSY`` — ``max_waiters <= 0`` and lock not acquired
    - ``SESSION_QUEUE_FULL`` — FIFO queue length already at cap
    - ``SESSION_LOCK_TIMEOUT`` — waited longer than ``max_wait_ms``
    """
    lock_key = f"{LOCK_KEY_PREFIX}{session_id}"
    queue_key = f"{QUEUE_KEY_PREFIX}{session_id}"

    got = await _eval_try_acquire_if_queue_empty(
        redis, lock_key, queue_key, ttl_seconds
    )
    if got == 1:
        return True, None

    if max_waiters <= 0:
        logger.warning("Session lock busy (no wait): %s", session_id)
        return False, "SESSION_BUSY"

    token = str(uuid.uuid4())
    if not await _eval_enqueue_waiter(redis, queue_key, max_waiters, token):
        logger.warning("Session chat queue full: %s", session_id)
        return False, "SESSION_QUEUE_FULL"

    await redis.expire(queue_key, max(ttl_seconds, 120))

    poll_s = max(0.05, poll_interval_ms / 1000.0)
    deadline = time.monotonic() + max_wait_ms / 1000.0

    try:
        while time.monotonic() < deadline:
            head = await redis.lindex(queue_key, 0)
            if head != token:
                await asyncio.sleep(poll_s)
                continue
            acquired = await redis.set(lock_key, "1", nx=True, ex=ttl_seconds)
            if acquired:
                popped = await redis.lpop(queue_key)
                if popped != token:
                    logger.warning(
                        "FIFO queue head mismatch session=%s expected=%s got=%s",
                        session_id,
                        token,
                        popped,
                    )
                logger.debug("Session lock acquired after wait: %s", session_id)
                return True, None
            await asyncio.sleep(poll_s)
        logger.warning("Session lock wait timeout: %s", session_id)
        await redis.lrem(queue_key, 1, token)
        return False, "SESSION_LOCK_TIMEOUT"
    except BaseException:
        await redis.lrem(queue_key, 1, token)
        raise
