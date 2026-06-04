"""Redis Streams queue for model inference requests (docs/10, docs/26).

P0: simplified priority queue using Redis sorted sets + stream.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from agent_factory.infra.redis import get_redis

logger = logging.getLogger(__name__)

QUEUE_STREAM = "mq:model_requests"
QUEUE_ZSET = "mq:model_queue"

# Priority classes (lower score = higher priority)
PRIORITY_MAP = {
    "privileged": 1,
    "interactive": 2,
    "document": 3,
    "batch": 4,
}


async def enqueue_model_request(
    *,
    run_id: str,
    session_id: str,
    agent_id: str,
    priority_class: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    timeout_seconds: int = 90,
    _redis=None,
) -> str:
    """Enqueue a model inference request and return job_id."""
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    redis = _redis or get_redis()
    score = PRIORITY_MAP.get(priority_class, 2)
    payload = {
        "job_id": job_id,
        "run_id": run_id,
        "session_id": session_id,
        "agent_id": agent_id,
        "priority_class": priority_class,
        "model": model,
        "messages": json.dumps(messages, ensure_ascii=False),
        "max_tokens": max_tokens,
        "timeout_seconds": timeout_seconds,
        "enqueued_at": datetime.now(UTC).isoformat(),
    }
    # Use zadd for priority ordering
    await redis.zadd(QUEUE_ZSET, {job_id: score})
    # Store payload in hash
    await redis.hset(f"job:{job_id}", mapping=payload)
    # Set TTL on job hash
    await redis.expire(f"job:{job_id}", timeout_seconds + 300)
    logger.debug("Enqueued model request %s (priority=%s)", job_id, priority_class)
    return job_id


async def dequeue_model_request(_redis=None) -> dict[str, Any] | None:
    """Pop highest priority job from queue. Returns None if empty."""
    redis = _redis or get_redis()
    # Get lowest score (highest priority) job
    items = await redis.zrange(QUEUE_ZSET, 0, 0, withscores=False)
    if not items:
        return None
    job_id = items[0]
    # Remove from queue
    await redis.zrem(QUEUE_ZSET, job_id)
    # Get payload
    payload = await redis.hgetall(f"job:{job_id}")
    if not payload:
        return None
    # Parse messages JSON
    if "messages" in payload:
        payload["messages"] = json.loads(payload["messages"])
    payload["job_id"] = job_id
    return payload


async def ack_model_request(job_id: str, _redis=None) -> None:
    """Acknowledge completed job and clean up."""
    redis = _redis or get_redis()
    await redis.delete(f"job:{job_id}")
    logger.debug("Acked model request %s", job_id)


async def get_queue_length(_redis=None) -> int:
    """Return total pending jobs."""
    redis = _redis or get_redis()
    return int(await redis.zcard(QUEUE_ZSET))
