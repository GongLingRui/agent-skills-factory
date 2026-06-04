"""Document parse job queue (Redis Stream ``mq:doc_jobs``)."""

from __future__ import annotations

import logging
from typing import Any

from redis.asyncio import Redis

from agent_factory.infra.redis import get_redis

logger = logging.getLogger(__name__)

# Must match ``document_parser_worker`` consumer (docs/24).
STREAM_KEY = "mq:doc_jobs"
GROUP_NAME = "doc-parser-workers"


async def ensure_doc_parser_consumer_group(redis: Redis) -> None:
    """Create the consumer group once (idempotent)."""
    try:
        await redis.xgroup_create(
            STREAM_KEY, GROUP_NAME, id="0", mkstream=True
        )
        logger.info("Created consumer group %s", GROUP_NAME)
    except Exception as exc:
        if "BUSYGROUP" in str(exc):
            logger.debug("Consumer group already exists")
        else:
            logger.warning("xgroup_create error: %s", exc)


async def doc_parse_queue_depth(redis: Redis | None = None) -> int:
    """Approximate pending stream depth (prd §9.5 doc parse queue > N)."""
    r = redis or get_redis()
    try:
        n = await r.xlen(STREAM_KEY)
        return int(n)
    except Exception:
        logger.exception("doc_parse_queue_depth xlen failed")
        return 0


async def enqueue_doc_parse_job(
    *,
    file_id: str,
    file_size: int,
    redis: Redis | None = None,
) -> str | None:
    """Push a parse job; large uploads call this (docs/24 size routing)."""
    r = redis or get_redis()
    entry_id = await r.xadd(
        STREAM_KEY,
        {"file_id": file_id, "size": str(file_size)},
    )
    logger.debug("Enqueued doc job %s for file_id=%s", entry_id, file_id)
    return entry_id if isinstance(entry_id, str) else str(entry_id)


def doc_job_fields(payload: dict[str, Any]) -> dict[str, object]:
    """Normalize stream fields from Redis (bytes vs str)."""
    out: dict[str, object] = {}
    for k, v in payload.items():
        key = k.decode() if isinstance(k, bytes) else str(k)
        if isinstance(v, bytes):
            out[key] = v.decode()
        else:
            out[key] = v
    return out
