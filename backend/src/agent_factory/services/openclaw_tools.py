"""Unified dispatcher for OpenClaw memory/sessions/ui/automation/media/runtime tools."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.core.user_context import UserContext
from agent_factory.db.models.run_spec import RunSpec
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.automation_tools import (
    AUTOMATION_TOOL_IDS,
    handle_automation_cron,
    handle_automation_gateway,
    handle_automation_heartbeat_respond,
)
from agent_factory.services.agents_plan_tools import (
    AGENTS_PLAN_TOOL_IDS,
    handle_agents_update_plan,
)
from agent_factory.services.code_execution_tools import (
    CODE_EXECUTION_TOOL_IDS,
    handle_code_execution,
)
from agent_factory.services.media_pdf_tts_tools import (
    MEDIA_PDF_TTS_TOOL_IDS,
    handle_media_pdf,
    handle_media_tts,
)
from agent_factory.services.media_tools import (
    MEDIA_TOOL_IDS,
    handle_media_image,
    handle_media_image_generate,
    handle_media_music_generate,
    handle_media_video_generate,
)
from agent_factory.services.messaging_tools import MESSAGING_TOOL_IDS, handle_messaging_message
from agent_factory.services.memory_tools import MEMORY_TOOL_IDS, handle_memory_get, handle_memory_search
from agent_factory.services.model_gateway import ModelGateway
from agent_factory.services.nodes_tools import NODES_TOOL_IDS, handle_nodes_manage
from agent_factory.services.process_tools import PROCESS_TOOL_IDS, handle_shell_process
from agent_factory.services.sessions_tools import (
    SESSIONS_TOOL_IDS,
    handle_sessions_history,
    handle_sessions_list,
    handle_sessions_send,
    handle_sessions_spawn,
    handle_sessions_status,
    handle_sessions_subagents,
    handle_sessions_yield,
)
from agent_factory.services.ui_tools import UI_TOOL_IDS, handle_ui_browser, handle_ui_canvas
from agent_factory.services.web_x_search_tools import WEB_X_SEARCH_TOOL_IDS, handle_web_x_search

OPENCLAW_RUNTIME_TOOL_IDS: frozenset[str] = (
    MEMORY_TOOL_IDS
    | SESSIONS_TOOL_IDS
    | UI_TOOL_IDS
    | AUTOMATION_TOOL_IDS
    | MEDIA_TOOL_IDS
    | PROCESS_TOOL_IDS
    | CODE_EXECUTION_TOOL_IDS
    | WEB_X_SEARCH_TOOL_IDS
    | MESSAGING_TOOL_IDS
    | NODES_TOOL_IDS
    | AGENTS_PLAN_TOOL_IDS
    | MEDIA_PDF_TTS_TOOL_IDS
)


async def dispatch_openclaw_tool_async(
    tool_id: str,
    params: dict[str, Any],
    *,
    db: AsyncSession,
    run_spec: RunSpec | None = None,
    session_id: str | None = None,
    user_ctx: UserContext | None = None,
    model_gateway: ModelGateway | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    if tool_id in MEMORY_TOOL_IDS:
        if run_spec is None or user_ctx is None:
            raise AgentFactoryException(
                "RUNSPEC_REQUIRED", f"{tool_id} requires run context", status_code=500
            )
        uid = user_ctx.user_id_hash or str(run_spec.user_id_hash or "")
        aid = str(run_spec.agent_id or "")
        if tool_id == "memory.search":
            return await handle_memory_search(
                db, params, user_id_hash=uid, agent_id=aid, settings=cfg
            )
        return await handle_memory_get(
            db, params, user_id_hash=uid, agent_id=aid, settings=cfg
        )

    if tool_id in SESSIONS_TOOL_IDS:
        if user_ctx is None or not session_id:
            raise AgentFactoryException(
                "USER_CONTEXT_REQUIRED",
                f"{tool_id} requires session context",
                status_code=500,
            )
        agent_id = str(run_spec.agent_id if run_spec else "") or ""
        sandboxed = bool((run_spec.runtime or {}).get("sandboxed")) if run_spec else False
        if tool_id == "sessions.list":
            return await handle_sessions_list(
                db,
                params,
                user_id_hash=user_ctx.user_id_hash,
                agent_id=agent_id,
                controller_session_id=session_id,
                sandboxed=sandboxed,
                settings=cfg,
            )
        if tool_id == "sessions.history":
            return await handle_sessions_history(
                db,
                params,
                user_id_hash=user_ctx.user_id_hash,
                agent_id=agent_id,
                controller_session_id=session_id,
                sandboxed=sandboxed,
                settings=cfg,
            )
        if tool_id == "sessions.send":
            return await handle_sessions_send(
                db,
                params,
                user_ctx=user_ctx,
                controller_session_id=session_id,
                agent_id=agent_id,
                sandboxed=sandboxed,
                settings=cfg,
            )
        if tool_id == "sessions.spawn":
            return await handle_sessions_spawn(
                db,
                params,
                user_ctx=user_ctx,
                controller_session_id=session_id,
                default_agent_id=agent_id,
                model_gateway=model_gateway,
                settings=cfg,
            )
        if tool_id == "sessions.yield":
            return await handle_sessions_yield(
                db, params, controller_session_id=session_id, settings=cfg
            )
        if tool_id == "sessions.subagents":
            return await handle_sessions_subagents(
                db, params, controller_session_id=session_id, settings=cfg
            )
        if tool_id == "sessions.status":
            return await handle_sessions_status(
                db,
                params,
                user_id_hash=user_ctx.user_id_hash,
                session_id=session_id,
                agent_id=agent_id,
                settings=cfg,
            )

    if tool_id in UI_TOOL_IDS:
        if tool_id == "ui.browser":
            return await handle_ui_browser(db, params, settings=cfg)
        if not session_id:
            raise AgentFactoryException(
                "SESSION_REQUIRED", "ui.canvas requires session_id", status_code=500
            )
        return await handle_ui_canvas(db, params, session_id=session_id, settings=cfg)

    if tool_id in AUTOMATION_TOOL_IDS:
        if tool_id == "automation.gateway":
            return await handle_automation_gateway(db, params, settings=cfg)
        if tool_id == "automation.heartbeat_respond":
            if not session_id:
                raise AgentFactoryException(
                    "SESSION_REQUIRED", f"{tool_id} requires session_id", status_code=500
                )
            return await handle_automation_heartbeat_respond(
                db, params, session_id=session_id, settings=cfg
            )
        if user_ctx is None:
            raise AgentFactoryException(
                "USER_CONTEXT_REQUIRED", "automation.cron requires user", status_code=500
            )
        agent_id = str(run_spec.agent_id if run_spec else "") or ""
        return await handle_automation_cron(
            db,
            params,
            user_id_hash=user_ctx.user_id_hash,
            agent_id=agent_id,
            session_id=session_id,
            settings=cfg,
        )

    if tool_id in MEDIA_TOOL_IDS:
        if tool_id == "media.image":
            model = None
            if run_spec and isinstance(run_spec.runtime, dict):
                model = run_spec.runtime.get("model")
            return await handle_media_image(
                db,
                params,
                model_gateway=model_gateway,
                agent_model=str(model) if model else None,
                settings=cfg,
            )
        if tool_id == "media.image_generate":
            return await handle_media_image_generate(db, params, settings=cfg)
        if tool_id == "media.music_generate":
            return await handle_media_music_generate(db, params, settings=cfg)
        if tool_id == "media.video_generate":
            return await handle_media_video_generate(db, params, settings=cfg)
        if tool_id == "media.pdf":
            model = None
            if run_spec and isinstance(run_spec.runtime, dict):
                model = run_spec.runtime.get("model")
            return await handle_media_pdf(
                db,
                params,
                model_gateway=model_gateway,
                agent_model=str(model) if model else None,
                settings=cfg,
            )
        if tool_id == "media.tts":
            return await handle_media_tts(
                db, params, session_id=session_id, settings=cfg
            )

    if tool_id in PROCESS_TOOL_IDS:
        return handle_shell_process(params, settings=cfg)

    if tool_id in CODE_EXECUTION_TOOL_IDS:
        return await handle_code_execution_async(
            params,
            model_gateway=model_gateway,
            run_spec=run_spec,
            settings=cfg,
        )

    if tool_id in WEB_X_SEARCH_TOOL_IDS:
        return await handle_web_x_search(params, settings=cfg)

    if tool_id in MESSAGING_TOOL_IDS:
        if not session_id:
            raise AgentFactoryException(
                "SESSION_REQUIRED", f"{tool_id} requires session_id", status_code=500
            )
        return await handle_messaging_message(
            db, params, session_id=session_id, settings=cfg
        )

    if tool_id in NODES_TOOL_IDS:
        return await handle_nodes_manage(params, settings=cfg)

    if tool_id in AGENTS_PLAN_TOOL_IDS:
        if not session_id:
            raise AgentFactoryException(
                "SESSION_REQUIRED", f"{tool_id} requires session_id", status_code=500
            )
        return await handle_agents_update_plan(
            db, params, session_id=session_id, settings=cfg
        )

    raise AgentFactoryException(
        "TOOL_NOT_IMPLEMENTED", f"OpenClaw tool not wired: {tool_id}", status_code=501
    )


async def handle_code_execution_async(
    params: dict[str, Any],
    *,
    model_gateway: ModelGateway | None,
    run_spec: RunSpec | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    if cfg.CODE_EXECUTION_URL:
        import httpx

        task = str(params.get("task") or "").strip()
        async with httpx.AsyncClient(timeout=float(cfg.CODE_EXECUTION_TIMEOUT_SECONDS)) as client:
            resp = await client.post(
                cfg.CODE_EXECUTION_URL.strip(),
                json={"task": task},
                headers=(
                    {"Authorization": f"Bearer {cfg.CODE_EXECUTION_API_KEY}"}
                    if cfg.CODE_EXECUTION_API_KEY
                    else {}
                ),
            )
            if resp.status_code >= 400:
                raise AgentFactoryException(
                    "UPSTREAM_ERROR",
                    f"code_execution upstream HTTP {resp.status_code}",
                    status_code=502,
                )
            return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"output": resp.text}

    task = str(params.get("task") or "").strip()
    if model_gateway and cfg.CODE_EXECUTION_LLM_FALLBACK:
        model = str((run_spec.runtime or {}).get("model") if run_spec else cfg.CODE_EXECUTION_MODEL or "MiniMax-M2.7")
        prompt = (
            "Write a single Python 3 script that completes the following task. "
            "Return ONLY executable Python code, no markdown fences.\n\n"
            f"Task:\n{task}"
        )
        parts: list[str] = []
        async for chunk in model_gateway.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.1,
            tools=None,
            concurrency_class="batch",
            queue_priority=3,
        ):
            for choice in chunk.choices:
                if choice.delta:
                    parts.append(choice.delta)
        code = "".join(parts).strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return handle_code_execution({**params, "task": code}, settings=cfg)

    return handle_code_execution(params, settings=cfg)
