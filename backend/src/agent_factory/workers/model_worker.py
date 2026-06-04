"""Model inference worker: dequeue from Redis priority queue and call ModelGateway."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_factory.infra.queue import (
    ack_model_request,
    dequeue_model_request,
)
from agent_factory.services.factory import get_model_gateway

logger = logging.getLogger(__name__)

BATCH_SIZE = 1
BLOCK_SECONDS = 5


async def _process_job(job: dict[str, Any]) -> dict[str, Any]:
    """Call model gateway for a single job and return result summary."""
    model = job.get("model", "MiniMax-M2.7")
    messages = job.get("messages", [])
    max_tokens = int(job.get("max_tokens", 8000))
    job_id = job.get("job_id", "unknown")

    gateway = get_model_gateway()
    try:
        chunks: list[str] = []
        async for chunk in gateway.chat(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
            tools=None,
        ):
            for choice in chunk.choices:
                if choice.delta:
                    chunks.append(choice.delta)

        text = "".join(chunks)
        return {
            "job_id": job_id,
            "status": "success",
            "output": text,
            "chunks": len(chunks),
        }
    except Exception as exc:
        logger.exception("Model call failed for job %s", job_id)
        return {
            "job_id": job_id,
            "status": "error",
            "error": str(exc)[:200],
        }


async def run_model_worker(
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Main model worker loop.

    Dequeues from Redis priority queue, calls ModelGateway, stores result.
    """
    logger.info("Model worker started")

    try:
        while shutdown_event is None or not shutdown_event.is_set():
            job = await dequeue_model_request()
            if job is None:
                await asyncio.sleep(0.5)
                continue

            result = await _process_job(job)
            await ack_model_request(job["job_id"])

            # P0: log result; later can push to Redis Stream or pub/sub
            logger.info(
                "Job %s finished: %s (%s chars)",
                result["job_id"],
                result["status"],
                len(result.get("output", "")),
            )
    finally:
        logger.info("Model worker stopped")
