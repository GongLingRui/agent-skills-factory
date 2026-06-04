"""Sub-agent spawn tool (OpenClaw sessions_spawn / Task parity)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.core.user_context import UserContext
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.model_gateway import ModelGateway

logger = logging.getLogger(__name__)

AGENT_TOOL_IDS: frozenset[str] = frozenset({"agent.spawn", "agent.list"})


async def handle_agent_list(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = settings or get_settings()
    q = str(params.get("query") or "").strip().lower()
    rows = await db.execute(
        select(AgentApp.id, AgentApp.name, AgentApp.description).where(
            AgentApp.lifecycle_state == "active"
        )
    )
    agents: list[dict[str, str]] = []
    for aid, name, desc in rows.all():
        hay = f"{aid} {name or ''} {desc or ''}".lower()
        if q and q not in hay:
            continue
        agents.append(
            {
                "id": str(aid),
                "name": str(name or aid),
                "description": str(desc or "")[:240],
            }
        )
    return {"agents": agents[:50], "total": len(agents)}


async def handle_agent_spawn(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    user_ctx: UserContext | None,
    model_gateway: ModelGateway | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run one model turn as a sub-agent and return text output."""
    cfg = settings or get_settings()
    agent_id = str(params.get("agent_id") or "").strip()
    prompt = str(params.get("prompt") or "").strip()
    description = str(params.get("description") or "").strip()
    if not agent_id or not prompt:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "agent_id and prompt are required",
            status_code=400,
        )
    if user_ctx is None:
        raise AgentFactoryException(
            "USER_CONTEXT_REQUIRED",
            "agent.spawn requires user context",
            status_code=500,
        )
    q = await db.execute(
        select(AgentApp).where(
            AgentApp.id == agent_id,
            AgentApp.lifecycle_state == "active",
        )
    )
    agent_row = q.scalar_one_or_none()
    if agent_row is None:
        raise AgentFactoryException(
            "NOT_FOUND",
            f"Agent not found: {agent_id}",
            status_code=404,
        )

    from agent_factory.services.compiler_service import CompilerService

    compiler = CompilerService(cfg)
    run_spec = await compiler.compile_and_save(
        db,
        agent_id=agent_id,
        user_ctx=user_ctx,
        runtime_overrides={"max_turns": 1},
    )
    system = "\n\n".join(
        p.get("content", "")
        for p in (run_spec.prompt_parts or [])
        if isinstance(p, dict) and p.get("content")
    ).strip()
    model = str((run_spec.runtime or {}).get("model") or "MiniMax-M2.7")
    gateway = model_gateway or ModelGateway(cfg)

    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    parts: list[str] = []
    async for chunk in gateway.chat(
        model=model,
        messages=messages,
        max_tokens=4000,
        temperature=0.3,
        tools=None,
        concurrency_class="batch",
        queue_priority=3,
    ):
        for choice in chunk.choices:
            if choice.delta:
                parts.append(choice.delta)
    output = "".join(parts).strip()

    return {
        "agent_id": agent_id,
        "agent_name": agent_row.name or agent_id,
        "description": description or None,
        "prompt": prompt,
        "output": output,
        "run_id": run_spec.run_id,
    }
