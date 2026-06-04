"""Cross-session rolling summary persistence (user × agent)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.core.context_memory import ContextMemorySettings
from agent_factory.db.models.user_agent_memory import UserAgentMemory
from agent_factory.services.model_gateway import ModelGateway

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _is_user_agent_memory_table_missing(exc: BaseException) -> bool:
    """True when DB has not applied migration ``20260512_0004`` yet."""
    text = str(exc).lower()
    return "user_agent_memory" in text and (
        "does not exist" in text or "undefinedtable" in text
    )


async def fetch_cross_session_summary(
    db: AsyncSession,
    *,
    user_id_hash: str,
    agent_id: str | None,
) -> str | None:
    """Return stored summary text, or None if absent / empty.

    Prefer segments JSONB rendering; fallback to summary_text.
    """
    aid = (agent_id or "").strip()
    if not aid:
        return None
    try:
        q = await db.execute(
            select(UserAgentMemory).where(
                UserAgentMemory.user_id_hash == user_id_hash,
                UserAgentMemory.agent_id == aid,
            )
        )
    except ProgrammingError as exc:
        if _is_user_agent_memory_table_missing(exc):
            logger.warning(
                "user_agent_memory table missing; run alembic upgrade head. "
                "Cross-session memory disabled for this request."
            )
            return None
        raise
    row = q.scalar_one_or_none()
    if row is None:
        return None

    # Prefer segments
    if row.segments and isinstance(row.segments, dict):
        return _render_segments(row.segments)

    text = str(row.summary_text or "").strip()
    return text or None


async def upsert_cross_session_summary(
    db: AsyncSession,
    *,
    user_id_hash: str,
    agent_id: str,
    summary_text: str,
    segments: dict[str, Any] | None = None,
    source_run_id: str | None,
) -> None:
    """Insert or update the rolling memory card (both text and segments)."""
    aid = agent_id.strip()
    if not aid:
        return
    try:
        q = await db.execute(
            select(UserAgentMemory).where(
                UserAgentMemory.user_id_hash == user_id_hash,
                UserAgentMemory.agent_id == aid,
            )
        )
    except ProgrammingError as exc:
        if _is_user_agent_memory_table_missing(exc):
            logger.warning(
                "user_agent_memory table missing; skip upsert. "
                "Run: cd backend && uv run alembic upgrade head"
            )
            return
        raise
    row = q.scalar_one_or_none()
    now = _utc_now()
    if row is None:
        db.add(
            UserAgentMemory(
                user_id_hash=user_id_hash,
                agent_id=aid,
                summary_text=summary_text,
                segments=segments,
                source_run_id=source_run_id,
                updated_at=now,
            )
        )
    else:
        row.summary_text = summary_text
        if segments is not None:
            row.segments = segments
        row.source_run_id = source_run_id
        row.updated_at = now
    await db.flush()


async def roll_forward_cross_session_memory(
    db: AsyncSession,
    model_gateway: ModelGateway,
    *,
    user_id_hash: str,
    agent_id: str | None,
    run_id: str | None,
    messages: list[dict[str, Any]],
    cfg: ContextMemorySettings,
    main_model: str,
) -> None:
    """Merge latest exchange into ``user_agent_memory`` (best-effort)."""
    from agent_factory.services.conversation_summarize import (
        format_messages_plain,
        merge_cross_session_segments,
        merge_cross_session_summary,
    )

    if not cfg.enabled or not cfg.cross_session_memory_enabled:
        return
    aid = (agent_id or "").strip()
    if not aid:
        return
    if len(messages) < 2:
        return

    tail = messages[-6:] if len(messages) > 6 else messages
    latest = format_messages_plain(
        [m for m in tail if isinstance(m, dict)],
        max_chars=16_000,
    )
    if not latest.strip():
        return

    smodel = cfg.summarization_model or main_model

    # Fetch existing row for segments
    prior_segments: dict[str, Any] | None = None
    prior_text: str | None = None
    try:
        q = await db.execute(
            select(UserAgentMemory).where(
                UserAgentMemory.user_id_hash == user_id_hash,
                UserAgentMemory.agent_id == aid,
            )
        )
        existing = q.scalar_one_or_none()
        if existing:
            prior_segments = existing.segments if isinstance(existing.segments, dict) else None
            prior_text = (existing.summary_text or "").strip() or None
    except ProgrammingError as exc:
        if _is_user_agent_memory_table_missing(exc):
            return
        raise

    merged_text = prior_text or ""
    merged_segments = dict(prior_segments) if prior_segments else {}

    try:
        if prior_segments is not None:
            merged_segments = await merge_cross_session_segments(
                model_gateway,
                model=smodel,
                prior_segments=prior_segments,
                latest_exchange=latest,
                max_out_tokens=cfg.summary_max_output_tokens,
            )
            merged_text = _render_segments(merged_segments)
        else:
            merged = await merge_cross_session_summary(
                model_gateway,
                model=smodel,
                prior_summary=prior_text or "",
                latest_exchange=latest,
                max_out_tokens=cfg.summary_max_output_tokens,
            )
            merged_text = merged
    except Exception:
        logger.exception("cross_session_memory_roll_forward_failed")
        return

    # Hard safety for DB row size
    _db_cap = 500_000
    if len(merged_text) > _db_cap:
        merged_text = merged_text[: _db_cap - 1] + "…"

    # Also cap segments text fields
    merged_segments = _cap_segments(merged_segments, _db_cap // 2)

    try:
        await upsert_cross_session_summary(
            db,
            user_id_hash=user_id_hash,
            agent_id=aid,
            summary_text=merged_text,
            segments=merged_segments,
            source_run_id=run_id,
        )
    except ProgrammingError as exc:
        if _is_user_agent_memory_table_missing(exc):
            logger.warning(
                "user_agent_memory table missing; cross-session write skipped."
            )
            return
        raise


def _render_segments(segments: dict[str, Any]) -> str:
    """Render segments dict to plain text."""
    parts: list[str] = []
    for key in ("facts", "preferences", "decisions", "todos"):
        vals = segments.get(key)
        if vals:
            parts.append(f"【{key}】")
            for v in vals:
                parts.append(f"- {v}")
    terms = segments.get("terms")
    if terms:
        parts.append("【terms】")
        for t in terms:
            if isinstance(t, dict):
                parts.append(f"- {t.get('name', '')}：{t.get('definition', '')}")
    return "\n".join(parts) if parts else ""


def _cap_segments(segments: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Cap total rendered size of segments."""
    out: dict[str, Any] = {}
    total = 0
    for key in ("facts", "preferences", "decisions", "todos"):
        vals = segments.get(key)
        if not isinstance(vals, list):
            continue
        kept: list[str] = []
        for v in vals:
            s = str(v)
            if total + len(s) > max_chars:
                break
            kept.append(s)
            total += len(s)
        out[key] = kept
    terms = segments.get("terms")
    if isinstance(terms, list):
        kept_terms: list[dict[str, str]] = []
        for t in terms:
            if isinstance(t, dict):
                s = f"{t.get('name', '')}：{t.get('definition', '')}"
                if total + len(s) > max_chars:
                    break
                kept_terms.append({"name": str(t.get("name") or ""), "definition": str(t.get("definition") or "")})
                total += len(s)
        out["terms"] = kept_terms
    return out
