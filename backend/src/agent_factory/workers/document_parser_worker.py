"""Document parser worker: consume Redis Stream doc_jobs (docs/24, docs/34).

Extracts plain text via ``document_text_extract`` and stores UTF-8 text at
``temp/{session_id}/extract_{file_id}.txt`` when MinIO succeeds.
"""

from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from agent_factory.config import get_settings
from agent_factory.core.document_text_extract import extract_plain_text
from agent_factory.db.models.file_upload import FileUpload
from agent_factory.infra.doc_queue import (
    GROUP_NAME,
    STREAM_KEY,
    doc_job_fields,
    ensure_doc_parser_consumer_group,
)
from agent_factory.infra.minio_client import MinioClient
from agent_factory.infra.redis import get_redis

logger = logging.getLogger(__name__)

CONSUMER_NAME = "worker-1"
BATCH_SIZE = 10
BLOCK_MS = 5000


async def _process_job(
    db: AsyncSession,
    redis: Redis,
    message_id: bytes,
    payload: dict[str, object],
) -> None:
    file_id = str(payload.get("file_id") or "")
    if not file_id:
        logger.warning("Job missing file_id, acking")
        await redis.xack(STREAM_KEY, GROUP_NAME, message_id)
        return

    result = await db.execute(
        select(FileUpload).where(FileUpload.file_id == file_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        logger.warning("FileUpload not found: %s", file_id)
        await redis.xack(STREAM_KEY, GROUP_NAME, message_id)
        return

    # P0: try MinIO fetch
    try:
        settings = get_settings()
        if row.storage_path:
            minio = MinioClient(settings)
            data = await minio.get_object(
                bucket=settings.MINIO_BUCKET,
                object_name=row.storage_path,
            )
            text = extract_plain_text(
                data,
                row.mime_type or "",
                file_name=row.file_name or "",
            )
            extract_path = (
                f"temp/{row.session_id}/extract_{row.file_id}.txt"
            )
            payload = text.encode("utf-8")
            try:
                await minio.put_object(
                    bucket=settings.MINIO_BUCKET,
                    object_name=extract_path,
                    data=payload,
                    length=len(payload),
                    content_type="text/plain; charset=utf-8",
                )
                row.extracted_text_path = extract_path
                row.status = "extracted"
                logger.info(
                    "Extracted file %s (%s chars, path=%s)",
                    file_id,
                    len(text),
                    extract_path,
                )
            except Exception:
                logger.exception(
                    "Storing extracted text failed for %s", file_id
                )
                row.extracted_text_path = None
                row.status = "failed"
        else:
            row.status = "failed"
            logger.warning("No storage_path for file %s", file_id)
    except Exception:
        logger.exception("Document extraction failed: %s", file_id)
        row.status = "failed"

    await db.flush()
    await redis.xack(STREAM_KEY, GROUP_NAME, message_id)


async def run_document_parser_worker(
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Main worker loop."""
    settings = get_settings()
    redis = get_redis()
    await ensure_doc_parser_consumer_group(redis)

    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=5,
        max_overflow=0,
    )
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )  # type: ignore[call-overload]

    logger.info("Document parser worker started")

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

            for _stream_name, entries in messages:
                for msg_id, fields in entries:
                    payload = doc_job_fields(dict(fields))
                    async with async_session() as db:
                        async with db.begin():
                            await _process_job(db, redis, msg_id, payload)
    finally:
        await engine.dispose()
        logger.info("Document parser worker stopped")
