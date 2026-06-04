"""OpenClaw cron / gateway automation tools."""

from __future__ import annotations

import logging
import platform
import sys
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.core.tool_catalog import TOOL_PRESETS, catalog_for_api, input_schema_for_tool
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.agent_cron_service import (
    compute_next_run,
    create_cron_job,
    get_cron_job,
    job_to_dict,
    list_cron_jobs,
)

logger = logging.getLogger(__name__)

AUTOMATION_TOOL_IDS: frozenset[str] = frozenset(
    {"automation.cron", "automation.gateway", "automation.heartbeat_respond"}
)

_HEARTBEAT_OUTCOMES = frozenset({"ok", "attention", "error", "skipped"})
_HEARTBEAT_PRIORITIES = frozenset({"low", "normal", "high"})

_CRON_ACTIONS = frozenset(
    {"status", "list", "get", "add", "update", "remove", "run", "runs", "wake"}
)

_GATEWAY_ACTIONS = frozenset(
    {"status", "config.get", "config.schema.lookup", "restart"}
)


def _require_automation_enabled(settings: Settings) -> None:
    if not settings.AUTOMATION_TOOLS_ENABLED:
        raise AgentFactoryException(
            "AUTOMATION_DISABLED",
            "automation tools disabled (set AUTOMATION_TOOLS_ENABLED=true)",
            status_code=503,
        )


async def handle_automation_cron(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    user_id_hash: str,
    agent_id: str,
    session_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    _require_automation_enabled(cfg)
    action = str(params.get("action") or "list").strip().lower()
    if action not in _CRON_ACTIONS:
        raise AgentFactoryException(
            "INVALID_PARAMS", f"Unknown cron action: {action}", status_code=400
        )

    if action == "status":
        jobs = await list_cron_jobs(db, user_id_hash=user_id_hash, agent_id=agent_id)
        enabled = sum(1 for j in jobs if j.enabled)
        return {
            "enabled": True,
            "jobCount": len(jobs),
            "enabledJobCount": enabled,
        }

    if action == "list":
        jobs = await list_cron_jobs(db, user_id_hash=user_id_hash, agent_id=agent_id)
        return {"jobs": [job_to_dict(j) for j in jobs], "total": len(jobs)}

    if action == "get":
        job_id = str(params.get("jobId") or params.get("job_id") or "").strip()
        if not job_id:
            raise AgentFactoryException(
                "INVALID_PARAMS", "jobId required", status_code=400
            )
        job = await get_cron_job(db, job_id, user_id_hash=user_id_hash)
        if job is None:
            raise AgentFactoryException("NOT_FOUND", "Job not found", status_code=404)
        return job_to_dict(job)

    if action == "add":
        name = str(params.get("name") or "scheduled task").strip()
        schedule = params.get("schedule")
        payload = params.get("payload")
        if not isinstance(schedule, dict) or not isinstance(payload, dict):
            flat = _recover_cron_object(params)
            schedule = flat.get("schedule") if isinstance(flat.get("schedule"), dict) else schedule
            payload = flat.get("payload") if isinstance(flat.get("payload"), dict) else payload
        if not isinstance(schedule, dict) or not isinstance(payload, dict):
            raise AgentFactoryException(
                "INVALID_PARAMS",
                "schedule and payload objects required",
                status_code=400,
            )
        job = await create_cron_job(
            db,
            user_id_hash=user_id_hash,
            agent_id=str(params.get("agentId") or agent_id),
            session_id=str(params.get("sessionId") or session_id or "") or None,
            name=name,
            description=str(params.get("description") or "")[:512] or None,
            schedule=schedule,
            payload=payload,
            delivery=params.get("delivery") if isinstance(params.get("delivery"), dict) else None,
            enabled=bool(params.get("enabled", True)),
            delete_after_run=bool(
                params.get("deleteAfterRun") or params.get("delete_after_run") or False
            ),
        )
        return {"status": "created", "job": job_to_dict(job)}

    if action == "update":
        job_id = str(params.get("jobId") or params.get("job_id") or "").strip()
        job = await get_cron_job(db, job_id, user_id_hash=user_id_hash) if job_id else None
        if job is None:
            raise AgentFactoryException("NOT_FOUND", "Job not found", status_code=404)
        if "enabled" in params:
            job.enabled = bool(params["enabled"])
        if isinstance(params.get("schedule"), dict):
            job.schedule = params["schedule"]
            job.next_run_at = compute_next_run(job.schedule)
        if isinstance(params.get("payload"), dict):
            job.payload = params["payload"]
        if "name" in params:
            job.name = str(params["name"])[:256]
        await db.flush()
        return {"status": "updated", "job": job_to_dict(job)}

    if action == "remove":
        job_id = str(params.get("jobId") or params.get("job_id") or "").strip()
        job = await get_cron_job(db, job_id, user_id_hash=user_id_hash) if job_id else None
        if job is None:
            raise AgentFactoryException("NOT_FOUND", "Job not found", status_code=404)
        await db.delete(job)
        await db.flush()
        return {"status": "removed", "jobId": job_id}

    if action == "run":
        job_id = str(params.get("jobId") or params.get("job_id") or "").strip()
        job = await get_cron_job(db, job_id, user_id_hash=user_id_hash) if job_id else None
        if job is None:
            raise AgentFactoryException("NOT_FOUND", "Job not found", status_code=404)
        from agent_factory.services.agent_cron_executor import execute_cron_job

        result = await execute_cron_job(db, job=job)
        return {"status": "ran", "jobId": job_id, "result": result}

    if action in ("runs", "wake"):
        return {
            "action": action,
            "status": "ok",
            "note": "Run history / wake queued (OpenClaw cron parity stub for runs/wake)",
        }

    raise AgentFactoryException("INVALID_PARAMS", f"Unhandled action {action}", status_code=400)


def _recover_cron_object(params: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "name",
        "schedule",
        "payload",
        "delivery",
        "enabled",
        "kind",
        "at",
        "every",
        "cron",
        "expr",
        "message",
    }
    out: dict[str, Any] = {}
    for k in keys:
        if k in params and params[k] is not None:
            out[k] = params[k]
    if "kind" in out and "schedule" not in out:
        out["schedule"] = {k: out[k] for k in ("kind", "at", "every", "cron", "expr") if k in out}
    if "message" in out and "payload" not in out:
        out["payload"] = {"kind": "agentTurn", "message": out["message"]}
    return out


async def handle_automation_gateway(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = db
    cfg = settings or get_settings()
    _require_automation_enabled(cfg)
    action = str(params.get("action") or "status").strip()
    if action not in _GATEWAY_ACTIONS:
        raise AgentFactoryException(
            "INVALID_PARAMS", f"Unknown gateway action: {action}", status_code=400
        )

    if action == "status":
        return {
            "status": "ok",
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "workspaceTools": cfg.WORKSPACE_TOOLS_ENABLED,
            "memoryTools": cfg.MEMORY_TOOLS_ENABLED,
            "sessionsTools": cfg.SESSIONS_TOOLS_ENABLED,
        }

    if action == "config.get":
        return {
            "presets": list(TOOL_PRESETS.keys()),
            "toolCatalog": catalog_for_api(settings=cfg),
        }

    if action == "config.schema.lookup":
        tool_id = str(params.get("toolId") or params.get("tool_id") or "").strip()
        if not tool_id:
            raise AgentFactoryException(
                "INVALID_PARAMS", "toolId required", status_code=400
            )
        return {"toolId": tool_id, "inputSchema": input_schema_for_tool(tool_id)}

    if action == "restart":
        return {
            "status": "deferred",
            "message": (
                "Gateway restart is not supported in API server mode; "
                "restart the backend process manually."
            ),
        }

    raise AgentFactoryException("INVALID_PARAMS", f"Unhandled action {action}", status_code=400)


async def handle_automation_heartbeat_respond(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    session_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    _require_automation_enabled(cfg)
    outcome = str(params.get("outcome") or "").strip().lower()
    if outcome not in _HEARTBEAT_OUTCOMES:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            f"outcome must be one of {sorted(_HEARTBEAT_OUTCOMES)}",
            status_code=400,
        )
    if "notify" not in params:
        raise AgentFactoryException(
            "INVALID_PARAMS", "notify (boolean) is required", status_code=400
        )
    notify = bool(params.get("notify"))
    summary = str(params.get("summary") or "").strip()
    if not summary:
        raise AgentFactoryException(
            "INVALID_PARAMS", "summary is required", status_code=400
        )
    notification_text = str(
        params.get("notificationText") or params.get("notification_text") or ""
    ).strip()
    if notify and not notification_text:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "notificationText required when notify=true",
            status_code=400,
        )
    reason = str(params.get("reason") or "").strip() or None
    priority = str(params.get("priority") or "normal").strip().lower()
    if priority not in _HEARTBEAT_PRIORITIES:
        priority = "normal"
    next_check = str(params.get("nextCheck") or params.get("next_check") or "").strip() or None

    from sqlalchemy import select
    from agent_factory.db.models.chat_session import ChatSession

    q = await db.execute(
        select(ChatSession).where(ChatSession.session_id == session_id)
    )
    session = q.scalar_one_or_none()
    if session is None:
        raise AgentFactoryException("NOT_FOUND", "Session not found", status_code=404)

    record = {
        "outcome": outcome,
        "notify": notify,
        "summary": summary,
        "notificationText": notification_text or None,
        "reason": reason,
        "priority": priority,
        "nextCheck": next_check,
    }
    ctx = dict(session.runtime_context or {})
    history = list(ctx.get("heartbeat_history") or [])
    history.append(record)
    ctx["heartbeat_history"] = history[-50:]
    ctx["last_heartbeat"] = record
    session.runtime_context = ctx
    await db.flush()

    return {"status": "recorded", **record}
