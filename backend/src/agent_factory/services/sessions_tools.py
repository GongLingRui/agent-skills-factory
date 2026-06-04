"""OpenClaw sessions_* / subagents / session_status tools."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.core.user_context import UserContext
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.db.models.checkpoint import Checkpoint
from agent_factory.db.models.run_spec import RunSpec
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.subagent_registry import (
    find_subagent_by_task_name,
    list_subagent_runs,
    register_subagent_run,
    set_yield_message,
    update_subagent_run,
)

logger = logging.getLogger(__name__)

SESSIONS_TOOL_IDS: frozenset[str] = frozenset(
    {
        "sessions.list",
        "sessions.history",
        "sessions.send",
        "sessions.spawn",
        "sessions.yield",
        "sessions.subagents",
        "sessions.status",
    }
)

_SESSION_KINDS = frozenset({"main", "subagent", "cron", "hook", "node", "other"})


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _require_sessions_enabled(settings: Settings) -> None:
    if not settings.SESSIONS_TOOLS_ENABLED:
        raise AgentFactoryException(
            "SESSIONS_DISABLED",
            "sessions tools are disabled (set SESSIONS_TOOLS_ENABLED=true)",
            status_code=503,
        )


def _strip_tool_messages(messages: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "")
        if role == "tool":
            continue
        out.append(m)
    return out


def _last_assistant_text(messages: list[dict[str, Any]]) -> str | None:
    for m in reversed(messages):
        if m.get("role") == "assistant":
            content = m.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
    return None


def _derive_title(messages: list[dict[str, Any]], fallback: str) -> str:
    for m in messages:
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                return c.strip()[:120]
    return fallback[:120]


async def _load_session_for_user(
    db: AsyncSession,
    session_id: str,
    *,
    user_id_hash: str,
) -> ChatSession:
    q = await db.execute(
        select(ChatSession).where(ChatSession.session_id == session_id)
    )
    row = q.scalar_one_or_none()
    if row is None:
        raise AgentFactoryException(
            "NOT_FOUND", f"Session not found: {session_id}", status_code=404
        )
    if row.user_id_hash != user_id_hash:
        raise AgentFactoryException(
            "FORBIDDEN", "Session not visible to caller", status_code=403
        )
    return row


async def _resolve_target_session(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    user_id_hash: str,
    default_agent_id: str,
    controller_session_id: str,
    restrict_to_spawned: bool = False,
) -> ChatSession:
    session_key = str(params.get("sessionKey") or params.get("session_id") or "").strip()
    label = str(params.get("label") or "").strip()
    agent_id = str(params.get("agentId") or params.get("agent_id") or "").strip()
    task_name = str(params.get("taskName") or params.get("task_name") or "").strip()

    if task_name:
        sub = await find_subagent_by_task_name(
            db,
            controller_session_id=controller_session_id,
            task_name=task_name,
        )
        if sub is None:
            raise AgentFactoryException(
                "NOT_FOUND",
                f"No subagent with taskName={task_name!r}",
                status_code=404,
            )
        return await _load_session_for_user(
            db, sub.child_session_id, user_id_hash=user_id_hash
        )

    if session_key:
        return await _load_session_for_user(
            db, session_key, user_id_hash=user_id_hash
        )

    filters = [ChatSession.user_id_hash == user_id_hash]
    if agent_id:
        filters.append(ChatSession.agent_id == agent_id)
    elif default_agent_id:
        filters.append(ChatSession.agent_id == default_agent_id)
    if label:
        filters.append(ChatSession.label == label)

    if restrict_to_spawned:
        filters.append(
            ChatSession.controller_session_id == controller_session_id
        )

    q = await db.execute(
        select(ChatSession).where(and_(*filters)).order_by(
            ChatSession.last_activity.desc()
        ).limit(1)
    )
    row = q.scalar_one_or_none()
    if row is None:
        raise AgentFactoryException(
            "NOT_FOUND",
            "Target session not found",
            status_code=404,
        )
    return row


async def _latest_checkpoint_messages(
    db: AsyncSession, run_id: str | None
) -> list[dict[str, Any]]:
    if not run_id:
        return []
    q = await db.execute(
        select(Checkpoint.messages)
        .where(Checkpoint.run_id == run_id)
        .order_by(Checkpoint.turn_number.desc(), Checkpoint.timestamp.desc())
        .limit(1)
    )
    raw = q.scalar_one_or_none()
    if not isinstance(raw, list):
        return []
    return _strip_tool_messages(raw)


async def handle_sessions_list(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    user_id_hash: str,
    agent_id: str,
    controller_session_id: str | None = None,
    sandboxed: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    _require_sessions_enabled(cfg)

    kinds_raw = params.get("kinds")
    allowed_kinds: set[str] | None = None
    if isinstance(kinds_raw, list) and kinds_raw:
        allowed_kinds = {
            str(k).lower()
            for k in kinds_raw
            if str(k).lower() in _SESSION_KINDS
        } or None

    limit = int(params.get("limit") or 50)
    limit = max(1, min(limit, 100))
    active_minutes = params.get("activeMinutes") or params.get("active_minutes")
    label = str(params.get("label") or "").strip()
    filter_agent = str(params.get("agentId") or params.get("agent_id") or "").strip()
    search = str(params.get("search") or "").strip().lower()
    include_titles = bool(
        params.get("includeDerivedTitles") or params.get("include_derived_titles")
    )
    include_last = bool(
        params.get("includeLastMessage") or params.get("include_last_message")
    )

    filters = [ChatSession.user_id_hash == user_id_hash]
    if filter_agent:
        filters.append(ChatSession.agent_id == filter_agent)
    elif agent_id:
        filters.append(ChatSession.agent_id == agent_id)
    if label:
        filters.append(ChatSession.label == label)
    if sandboxed and controller_session_id:
        filters.append(
            or_(
                ChatSession.session_id == controller_session_id,
                ChatSession.controller_session_id == controller_session_id,
            )
        )
    if active_minutes is not None:
        cutoff = _utc_now() - timedelta(minutes=max(1, int(active_minutes)))
        filters.append(ChatSession.last_activity >= cutoff)

    q = await db.execute(
        select(ChatSession)
        .where(and_(*filters))
        .order_by(ChatSession.last_activity.desc())
        .limit(limit * 3)
    )
    rows = list(q.scalars().all())

    sessions_out: list[dict[str, Any]] = []
    for row in rows:
        kind = str(row.session_kind or "main")
        if allowed_kinds and kind not in allowed_kinds:
            continue
        title = row.title
        last_message: str | None = None
        if include_titles or include_last:
            msgs = await _latest_checkpoint_messages(db, row.run_id)
            if include_titles and not title:
                title = _derive_title(msgs, row.session_id)
            if include_last:
                last_message = _last_assistant_text(msgs)
        hay = f"{row.session_id} {row.label or ''} {title or ''} {row.agent_id or ''}".lower()
        if search and search not in hay:
            continue
        sessions_out.append(
            {
                "sessionId": row.session_id,
                "sessionKey": row.session_id,
                "agentId": row.agent_id,
                "kind": kind,
                "label": row.label,
                "title": title,
                "status": row.status,
                "runStatus": row.run_status,
                "turnCount": row.turn_count,
                "lastActivity": row.last_activity.isoformat() if row.last_activity else None,
                "lastMessage": last_message,
                "parentSessionId": row.parent_session_id,
            }
        )
        if len(sessions_out) >= limit:
            break

    return {"sessions": sessions_out, "total": len(sessions_out)}


async def handle_sessions_history(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    user_id_hash: str,
    agent_id: str,
    controller_session_id: str,
    sandboxed: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    _require_sessions_enabled(cfg)
    target = await _resolve_target_session(
        db,
        params,
        user_id_hash=user_id_hash,
        default_agent_id=agent_id,
        controller_session_id=controller_session_id,
        restrict_to_spawned=sandboxed,
    )
    message_limit = int(params.get("messageLimit") or params.get("message_limit") or 50)
    message_limit = max(0, min(message_limit, 200))
    msgs = await _latest_checkpoint_messages(db, target.run_id)
    if message_limit:
        msgs = msgs[-message_limit:]
    max_chars = int(cfg.SESSIONS_HISTORY_MAX_CHARS)
    serialized = str(msgs)
    truncated = len(serialized) > max_chars
    if truncated:
        msgs = msgs[-max(1, message_limit // 2) :]
    return {
        "sessionId": target.session_id,
        "agentId": target.agent_id,
        "messages": msgs,
        "truncated": truncated,
        "messageCount": len(msgs),
    }


async def handle_sessions_send(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    user_ctx: UserContext,
    controller_session_id: str,
    agent_id: str,
    sandboxed: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    _require_sessions_enabled(cfg)
    message = str(params.get("message") or "").strip()
    if not message:
        raise AgentFactoryException(
            "INVALID_PARAMS", "message is required", status_code=400
        )
    timeout = float(params.get("timeoutSeconds") or params.get("timeout_seconds") or 120)
    timeout = max(0.0, min(timeout, float(cfg.SESSIONS_SEND_MAX_TIMEOUT_SECONDS)))

    target = await _resolve_target_session(
        db,
        params,
        user_id_hash=user_ctx.user_id_hash,
        default_agent_id=agent_id,
        controller_session_id=controller_session_id,
        restrict_to_spawned=sandboxed,
    )
    if not target.run_id or not target.agent_id:
        raise AgentFactoryException(
            "INVALID_STATE",
            "Target session has no active run",
            status_code=409,
        )

    from agent_factory.services.factory import get_runner_service

    q = await db.execute(select(RunSpec).where(RunSpec.run_id == target.run_id))
    run_spec = q.scalar_one_or_none()
    if run_spec is None:
        raise AgentFactoryException(
            "NOT_FOUND", "RunSpec not found for target session", status_code=404
        )

    runner = get_runner_service()
    gateway = get_model_gateway()
    annotated = (
        f"[Inter-session message from {controller_session_id}]\n\n{message}"
    )

    if timeout <= 0:
        asyncio.create_task(
            _run_send_background(
                target_session_id=target.session_id,
                run_spec_id=target.run_id,
                message=annotated,
                user_ctx=user_ctx,
            )
        )
        return {
            "sessionId": target.session_id,
            "status": "queued",
            "reply": None,
        }

    result = await runner.run_turn_background(
        db=db,
        run_spec=run_spec,
        session=target,
        user_message=annotated,
        caller_permissions=frozenset(user_ctx.permissions),
    )
    target.last_activity = _utc_now()
    target.run_status = "done" if not result.get("errors") else "failed"
    await db.flush()
    return {
        "sessionId": target.session_id,
        "status": "done" if not result.get("errors") else "failed",
        "reply": result.get("output") or "",
        "errors": result.get("errors") or [],
    }


async def _run_send_background(
    *,
    target_session_id: str,
    run_spec_id: str,
    message: str,
    user_ctx: UserContext,
) -> None:
    from agent_factory.infra.db import get_session_factory
    from agent_factory.services.factory import get_runner_service

    factory = get_session_factory()
    async with factory() as db:
        try:
            q_sess = await db.execute(
                select(ChatSession).where(ChatSession.session_id == target_session_id)
            )
            session = q_sess.scalar_one_or_none()
            q_rs = await db.execute(
                select(RunSpec).where(RunSpec.run_id == run_spec_id)
            )
            run_spec = q_rs.scalar_one_or_none()
            if session is None or run_spec is None:
                return
            runner = get_runner_service()
            await runner.run_turn_background(
                db=db,
                run_spec=run_spec,
                session=session,
                user_message=message,
                caller_permissions=frozenset(user_ctx.permissions),
            )
            await db.commit()
        except Exception:
            logger.exception("sessions.send background failed")


async def handle_sessions_spawn(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    user_ctx: UserContext,
    controller_session_id: str,
    default_agent_id: str,
    model_gateway: Any | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    _require_sessions_enabled(cfg)
    task = str(params.get("task") or params.get("prompt") or "").strip()
    if not task:
        raise AgentFactoryException(
            "INVALID_PARAMS", "task is required", status_code=400
        )
    target_agent = str(
        params.get("agentId") or params.get("agent_id") or default_agent_id
    ).strip()
    label = str(params.get("label") or "").strip() or None
    task_name = str(params.get("taskName") or params.get("task_name") or "").strip() or None
    runtime = str(params.get("runtime") or "subagent").strip().lower()
    wait = bool(params.get("waitForReply") or params.get("wait_for_reply", True))
    timeout = float(
        params.get("runTimeoutSeconds")
        or params.get("timeoutSeconds")
        or params.get("timeout_seconds")
        or 180
    )
    timeout = max(5.0, min(timeout, float(cfg.SESSIONS_SPAWN_MAX_TIMEOUT_SECONDS)))

    q = await db.execute(
        select(AgentApp).where(
            AgentApp.id == target_agent,
            AgentApp.lifecycle_state == "active",
        )
    )
    agent_row = q.scalar_one_or_none()
    if agent_row is None:
        raise AgentFactoryException(
            "NOT_FOUND", f"Agent not found: {target_agent}", status_code=404
        )

    from agent_factory.services.compiler_service import CompilerService
    from agent_factory.services.factory import get_model_gateway, get_runner_service

    child_sid = f"sess_{uuid.uuid4().hex}"
    now = _utc_now()
    runtime_overrides: dict[str, Any] = {"max_turns": 10}
    model_override = params.get("model")
    if isinstance(model_override, str) and model_override.strip():
        runtime_overrides["model"] = model_override.strip()

    compiler = CompilerService(cfg)
    run_spec = await compiler.compile_and_save(
        db,
        agent_id=target_agent,
        user_ctx=user_ctx,
        runtime_overrides=runtime_overrides,
    )

    child = ChatSession(
        session_id=child_sid,
        run_id=run_spec.run_id,
        user_id_hash=user_ctx.user_id_hash,
        agent_id=target_agent,
        department=user_ctx.department,
        status="running",
        turn_count=0,
        total_tokens=0,
        created_at=now,
        last_activity=now,
        expires_at=now + timedelta(days=7),
        session_kind="subagent" if runtime == "subagent" else "other",
        label=label,
        parent_session_id=controller_session_id,
        controller_session_id=controller_session_id,
        run_status="running",
    )
    db.add(child)

    sub_run = await register_subagent_run(
        db,
        controller_session_id=controller_session_id,
        child_session_id=child_sid,
        agent_id=target_agent,
        user_id_hash=user_ctx.user_id_hash,
        task_name=task_name,
        label=label,
        description=str(params.get("description") or "")[:500] or None,
    )

    if not wait:
        asyncio.create_task(
            _spawn_run_background(
                sub_run_id=sub_run.run_id,
                child_session_id=child_sid,
                run_spec_id=run_spec.run_id,
                task=task,
                user_ctx=user_ctx,
            )
        )
        return {
            "status": "accepted",
            "runtime": runtime,
            "sessionId": child_sid,
            "sessionKey": child_sid,
            "runId": sub_run.run_id,
            "agentId": target_agent,
        }

    runner = get_runner_service()
    result = await runner.run_turn_background(
        db=db,
        run_spec=run_spec,
        session=child,
        user_message=task,
        caller_permissions=frozenset(user_ctx.permissions),
    )
    output = str(result.get("output") or "")
    status = "done" if not result.get("errors") else "failed"
    child.run_status = status
    child.last_activity = _utc_now()
    await update_subagent_run(
        db,
        sub_run.run_id,
        status=status,
        output=output,
        error=(
            str(result["errors"][0]) if result.get("errors") else None
        ),
    )
    return {
        "status": status,
        "runtime": runtime,
        "sessionId": child_sid,
        "sessionKey": child_sid,
        "runId": sub_run.run_id,
        "agentId": target_agent,
        "output": output,
        "errors": result.get("errors") or [],
    }


async def _spawn_run_background(
    *,
    sub_run_id: str,
    child_session_id: str,
    run_spec_id: str,
    task: str,
    user_ctx: UserContext,
) -> None:
    from agent_factory.infra.db import get_session_factory
    from agent_factory.services.factory import get_runner_service

    factory = get_session_factory()
    async with factory() as db:
        try:
            await update_subagent_run(db, sub_run_id, status="running")
            q_sess = await db.execute(
                select(ChatSession).where(ChatSession.session_id == child_session_id)
            )
            session = q_sess.scalar_one_or_none()
            q_rs = await db.execute(
                select(RunSpec).where(RunSpec.run_id == run_spec_id)
            )
            run_spec = q_rs.scalar_one_or_none()
            if session is None or run_spec is None:
                await update_subagent_run(
                    db, sub_run_id, status="failed", error="session or runspec missing"
                )
                await db.commit()
                return
            runner = get_runner_service()
            result = await runner.run_turn_background(
                db=db,
                run_spec=run_spec,
                session=session,
                user_message=task,
                caller_permissions=frozenset(user_ctx.permissions),
            )
            status = "done" if not result.get("errors") else "failed"
            session.run_status = status
            await update_subagent_run(
                db,
                sub_run_id,
                status=status,
                output=str(result.get("output") or ""),
                error=(
                    str(result["errors"][0]) if result.get("errors") else None
                ),
            )
            await db.commit()
        except Exception as exc:
            logger.exception("sessions.spawn background failed")
            await update_subagent_run(
                db, sub_run_id, status="failed", error=str(exc)
            )
            await db.commit()


async def handle_sessions_yield(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    controller_session_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    _require_sessions_enabled(cfg)
    message = str(params.get("message") or "").strip()
    run_id = str(params.get("runId") or params.get("run_id") or "").strip()
    if not message:
        raise AgentFactoryException(
            "INVALID_PARAMS", "message is required", status_code=400
        )
    if not run_id:
        subs = await list_subagent_runs(
            db, controller_session_id=controller_session_id, limit=1
        )
        if not subs:
            raise AgentFactoryException(
                "NOT_FOUND", "No subagent run to yield", status_code=404
            )
        run_id = subs[0].run_id
    await set_yield_message(db, run_id=run_id, message=message)
    return {"status": "yielded", "runId": run_id, "message": message}


async def handle_sessions_subagents(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    controller_session_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = params
    cfg = settings or get_settings()
    _require_sessions_enabled(cfg)
    rows = await list_subagent_runs(
        db, controller_session_id=controller_session_id, limit=50
    )
    agents = [
        {
            "runId": r.run_id,
            "sessionId": r.child_session_id,
            "agentId": r.agent_id,
            "taskName": r.task_name,
            "label": r.label,
            "status": r.status,
            "output": (r.output or "")[:2000] if r.output else None,
            "yieldMessage": r.yield_message,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {"subagents": agents, "total": len(agents)}


async def handle_sessions_status(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    user_id_hash: str,
    session_id: str,
    agent_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    _require_sessions_enabled(cfg)
    target_key = str(
        params.get("sessionKey") or params.get("session_id") or "current"
    ).strip()
    if target_key in ("current", ""):
        target_key = session_id
    target = await _load_session_for_user(
        db, target_key, user_id_hash=user_id_hash
    )
    msgs = await _latest_checkpoint_messages(db, target.run_id)
    return {
        "sessionId": target.session_id,
        "sessionKey": target.session_id,
        "agentId": target.agent_id or agent_id,
        "kind": target.session_kind,
        "label": target.label,
        "title": target.title or _derive_title(msgs, target.session_id),
        "status": target.status,
        "runStatus": target.run_status,
        "turnCount": target.turn_count,
        "runId": target.run_id,
        "lastActivity": target.last_activity.isoformat() if target.last_activity else None,
        "messageCount": len(msgs),
    }
