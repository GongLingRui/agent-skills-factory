"""Audit worker: consume Redis Stream mq:audit and write to PG (docs/12, docs/26)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from agent_factory.config import get_settings
from agent_factory.db.models.audit import AuditLog
from agent_factory.infra.redis import get_redis

logger = logging.getLogger(__name__)

STREAM_KEY = "mq:audit"
GROUP_NAME = "audit-workers"
CONSUMER_NAME = "worker-1"
BATCH_SIZE = 50
BLOCK_MS = 5000
MAX_RETRIES = 3


async def _ensure_consumer_group(redis: Redis) -> None:
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


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _process_batch(
    db: AsyncSession,
    redis: Redis,
    items: list[tuple[bytes, dict[str, object]]],
) -> None:
    """Insert batch of audit logs and ack successful ones."""
    ack_ids: list[bytes] = []
    for msg_id, fields in items:
        try:
            payload: dict[str, object] = dict(fields)  # type: ignore[arg-type]
            row = AuditLog(
                run_id=str(payload.get("run_id") or "") or None,
                session_id=str(payload.get("session_id") or "") or None,
                timestamp=_parse_timestamp(
                    str(payload.get("timestamp") or "")
                )
                or datetime.now(UTC).replace(tzinfo=None),
                level=str(payload.get("level") or "").lower() or None,
                user_id_hash=str(payload.get("user_id_hash") or "") or None,
                agent_id=str(payload.get("agent_id") or "") or None,
                department=str(payload.get("department") or "") or None,
                tool_calls=payload.get("tool_calls"),
                token_count=(
                    int(payload["token_count"])
                    if "token_count" in payload
                    else None
                ),
                cost=float(payload["cost"]) if "cost" in payload else None,
                error_code=str(payload.get("error_code") or "") or None,
                retrieval_ids=payload.get("retrieval_ids"),
                prompt_summary=str(payload.get("prompt_summary") or "") or None,
                retrieval_hits=payload.get("retrieval_hits"),
                full_prompt=str(payload.get("full_prompt") or "") or None,
                full_output=str(payload.get("full_output") or "") or None,
                retention_until=_parse_timestamp(
                    str(payload.get("retention_until") or "")
                ),
                status="active",
            )
            db.add(row)
            ack_ids.append(msg_id)
        except Exception:
            logger.exception("Failed to parse audit message %s", msg_id)
            # Do not ack; message will be redelivered to another consumer

    if ack_ids:
        await db.flush()
        for msg_id in ack_ids:
            try:
                await redis.xack(STREAM_KEY, GROUP_NAME, msg_id)
            except Exception:
                logger.exception("Failed to ack audit message %s", msg_id)


async def run_audit_worker(
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Main audit worker loop."""
    settings = get_settings()
    redis = get_redis()
    await _ensure_consumer_group(redis)

    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=5,
        max_overflow=0,
    )
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )  # type: ignore[call-overload]

    logger.info("Audit worker started")

    try:
        while shutdown_event is None or not shutdown_event.is_set():
            try:
                messages = await redis.xreadgroup(
                    groupname=GROUP_NAME,
                    consumername=CONSUMER_NAME,
                    streams={STREAM_KEY: ">"},
                    count=BATCH_SIZE,
                    block=BLOCK_MS,
                )
            except Exception:
                logger.exception("xreadgroup error")
                await asyncio.sleep(1)
                continue

            if not messages:
                continue

            batch: list[tuple[bytes, dict[str, object]]] = []
            for _stream_name, entries in messages:
                for msg_id, fields in entries:
                    batch.append((msg_id, dict(fields)))  # type: ignore[arg-type]

            if batch:
                async with async_session() as db:
                    async with db.begin():
                        await _process_batch(db, redis, batch)
    finally:
        await engine.dispose()
        logger.info("Audit worker stopped")
