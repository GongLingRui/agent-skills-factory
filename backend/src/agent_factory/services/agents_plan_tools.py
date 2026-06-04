"""OpenClaw update_plan tool — agent task plan in session state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.middleware.error_handler import AgentFactoryException

AGENTS_PLAN_TOOL_IDS: frozenset[str] = frozenset({"agents.update_plan"})

_PLAN_STATUSES = frozenset({"pending", "in_progress", "completed"})


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _parse_plan(params: dict[str, Any]) -> list[dict[str, str]]:
    raw = params.get("plan")
    if not isinstance(raw, list) or not raw:
        raise AgentFactoryException(
            "INVALID_PARAMS", "plan array is required", status_code=400
        )
    steps: list[dict[str, str]] = []
    in_progress = 0
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise AgentFactoryException(
                "INVALID_PARAMS", f"plan[{i}] must be object", status_code=400
            )
        step = str(entry.get("step") or "").strip()
        status = str(entry.get("status") or "").strip().lower()
        if not step:
            raise AgentFactoryException(
                "INVALID_PARAMS", f"plan[{i}].step required", status_code=400
            )
        if status not in _PLAN_STATUSES:
            raise AgentFactoryException(
                "INVALID_PARAMS",
                f"plan[{i}].status must be pending|in_progress|completed",
                status_code=400,
            )
        if status == "in_progress":
            in_progress += 1
        steps.append({"step": step, "status": status})
    if in_progress > 1:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "plan can contain at most one in_progress step",
            status_code=400,
        )
    return steps


async def handle_agents_update_plan(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    session_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = settings or get_settings()
    plan = _parse_plan(params)
    explanation = str(params.get("explanation") or "").strip() or None

    q = await db.execute(
        select(ChatSession).where(ChatSession.session_id == session_id)
    )
    session = q.scalar_one_or_none()
    if session is None:
        raise AgentFactoryException("NOT_FOUND", "Session not found", status_code=404)

    ctx = dict(session.runtime_context or {})
    ctx["agent_plan"] = {
        "plan": plan,
        "explanation": explanation,
        "updatedAt": _utc_now().isoformat(),
    }
    session.runtime_context = ctx
    await db.flush()

    return {
        "status": "updated",
        "explanation": explanation,
        "plan": plan,
    }
