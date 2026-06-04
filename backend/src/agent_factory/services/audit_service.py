"""Audit event delivery: async via Redis Stream (docs/12, docs/34)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from agent_factory.infra.redis import get_redis

logger = logging.getLogger(__name__)

STREAM_KEY = "mq:audit"
_ELEVATE_KEY = "audit:elevate:{run_id}"


async def set_audit_elevation(*, run_id: str, level: str, ttl_seconds: int = 3600) -> None:
    """Mark a run for elevated audit rows (e.g. after prompt-risk heuristics)."""
    if not run_id:
        return
    try:
        redis = get_redis()
        await redis.setex(
            _ELEVATE_KEY.format(run_id=run_id),
            ttl_seconds,
            level,
        )
    except Exception:
        logger.exception("audit_elevation_set_failed")


async def _effective_level(run_id: str | None, base_level: str) -> str:
    if not run_id:
        return base_level
    try:
        redis = get_redis()
        raw = await redis.get(_ELEVATE_KEY.format(run_id=run_id))
        if raw in (b"standard", "standard"):
            if base_level == "minimal":
                return "standard"
        if raw in (b"full", "full"):
            return "full"
    except Exception:
        logger.exception("audit_elevation_read_failed")
    return base_level


async def push_audit_event(
    *,
    run_id: str | None,
    session_id: str | None,
    user_id_hash: str | None,
    agent_id: str | None,
    department: str | None,
    tool_calls: list[dict[str, Any]] | None,
    token_count: int | None,
    error_code: str | None,
    retrieval_ids: list[str] | None,
    base_audit_level: str = "minimal",
    prompt_summary: str | None = None,
    full_prompt: str | None = None,
    full_output: str | None = None,
) -> None:
    """Push audit event to Redis Stream for async write to PG."""
    try:
        redis = get_redis()
        level = await _effective_level(run_id, base_audit_level)
        event: dict[str, Any] = {
            "run_id": run_id,
            "session_id": session_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "user_id_hash": user_id_hash,
            "agent_id": agent_id,
            "department": department,
            "tool_calls": json.dumps(tool_calls) if tool_calls else None,
            "token_count": token_count,
            "error_code": error_code,
            "retrieval_ids": json.dumps(retrieval_ids) if retrieval_ids else None,
        }
        if level == "standard" and prompt_summary:
            event["prompt_summary"] = prompt_summary[:2000]
        if level == "full":
            if prompt_summary:
                event["prompt_summary"] = prompt_summary[:2000]
            if full_prompt:
                event["full_prompt"] = full_prompt[:200_000]
            if full_output:
                event["full_output"] = full_output[:200_000]
        payload = {k: v for k, v in event.items() if v is not None}
        await redis.xadd(STREAM_KEY, payload)
    except Exception:
        logger.exception("Failed to push audit event")
