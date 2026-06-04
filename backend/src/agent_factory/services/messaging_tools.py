"""OpenClaw message tool — outbound messaging for chat sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.db.models.checkpoint import Checkpoint
from agent_factory.middleware.error_handler import AgentFactoryException

MESSAGING_TOOL_IDS: frozenset[str] = frozenset({"messaging.message"})

_MESSAGE_ACTIONS = frozenset({"send", "read", "broadcast"})


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def handle_messaging_message(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    session_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    if not cfg.MESSAGING_TOOLS_ENABLED:
        raise AgentFactoryException(
            "MESSAGING_DISABLED",
            "messaging.message disabled (set MESSAGING_TOOLS_ENABLED=true)",
            status_code=503,
        )
    action = str(params.get("action") or "send").strip().lower()
    if action not in _MESSAGE_ACTIONS:
        raise AgentFactoryException(
            "INVALID_PARAMS", f"Unknown action: {action}", status_code=400
        )

    q = await db.execute(
        select(ChatSession).where(ChatSession.session_id == session_id)
    )
    session = q.scalar_one_or_none()
    if session is None:
        raise AgentFactoryException("NOT_FOUND", "Session not found", status_code=404)

    if action == "read":
        limit = int(params.get("limit") or params.get("messageLimit") or 20)
        msgs: list[dict[str, Any]] = []
        if session.run_id:
            cp_q = await db.execute(
                select(Checkpoint.messages)
                .where(Checkpoint.run_id == session.run_id)
                .order_by(Checkpoint.turn_number.desc())
                .limit(1)
            )
            raw = cp_q.scalar_one_or_none()
            if isinstance(raw, list):
                msgs = [m for m in raw if isinstance(m, dict)][-limit:]
        ctx = session.runtime_context if isinstance(session.runtime_context, dict) else {}
        outbound = ctx.get("outbound_messages") or []
        return {
            "action": "read",
            "sessionId": session_id,
            "checkpointMessages": msgs,
            "outboundMessages": outbound[-limit:] if isinstance(outbound, list) else [],
        }

    text = str(params.get("message") or params.get("text") or params.get("content") or "").strip()
    if not text:
        raise AgentFactoryException(
            "INVALID_PARAMS", "message text is required", status_code=400
        )
    channel = str(params.get("channel") or "chat").strip()
    dry_run = bool(params.get("dryRun") or params.get("dry_run"))

    entry = {
        "channel": channel,
        "text": text,
        "timestamp": _utc_now().isoformat(),
        "action": action,
    }
    if dry_run:
        return {"status": "dry_run", "wouldSend": entry}

    ctx = dict(session.runtime_context or {})
    outbound = list(ctx.get("outbound_messages") or [])
    outbound.append(entry)
    ctx["outbound_messages"] = outbound[-100:]
    ctx["last_outbound"] = entry
    session.runtime_context = ctx
    session.last_activity = _utc_now()
    await db.flush()

    return {
        "status": "sent",
        "action": action,
        "sessionId": session_id,
        "channel": channel,
        "messageId": f"msg_{len(outbound)}",
        "length": len(text),
    }
