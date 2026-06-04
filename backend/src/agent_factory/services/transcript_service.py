"""Transcript event recording service."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.db.models.transcript import TranscriptEvent
from agent_factory.utils.analytics_guard import sanitize_for_analytics

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def record_event(
    db: AsyncSession,
    *,
    run_id: str,
    session_id: str,
    turn_number: int,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Best-effort write a transcript event (swallowed on DB error)."""
    try:
        safe_payload = _sanitize_payload(payload)
        evt = TranscriptEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            run_id=run_id,
            session_id=session_id,
            turn_number=turn_number,
            event_type=event_type,
            payload=safe_payload,
            timestamp=_utc_now(),
        )
        db.add(evt)
        await db.flush()
    except Exception:
        logger.exception("transcript_record_event_failed")
        # Ensure the transaction is not left in an aborted state.
        try:
            await db.rollback()
        except Exception:
            pass


def _sanitize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Redact potential PII from string fields in *payload*."""
    if not payload:
        return {}
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, str):
            out[k] = sanitize_for_analytics(v)
        elif isinstance(v, dict):
            out[k] = _sanitize_payload(v)
        elif isinstance(v, list):
            out[k] = [
                sanitize_for_analytics(i) if isinstance(i, str) else i
                for i in v
            ]
        else:
            out[k] = v
    return out
