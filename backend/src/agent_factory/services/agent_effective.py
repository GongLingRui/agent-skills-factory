"""Resolve which Agent snapshot to compile under release strategy (docs/03)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.core.user_context import UserContext
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.db.models.agent_version import AgentVersion

logger = logging.getLogger(__name__)


def _compiler_dict_from_app_row(agent: AgentApp) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "version": agent.version,
        "instruction": agent.instruction,
        "model_policy": agent.model_policy,
        "skill_config": agent.skill_config,
        "tools_allow": agent.tools_allow,
        "knowledge_scopes": agent.knowledge_scopes,
        "output_schema": agent.output_schema,
        "limits_config": agent.limits_config,
        "audit_config": agent.audit_config,
        "enterprise_config": agent.enterprise_config,
        "ui_config": agent.ui_config,
        "tags": agent.tags,
    }


def _compiler_dict_from_version(agent_id: str, ver: AgentVersion) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": ver.name,
        "version": ver.version,
        "instruction": ver.instruction,
        "model_policy": ver.model_policy,
        "skill_config": ver.skill_config,
        "tools_allow": ver.tools_allow,
        "knowledge_scopes": ver.knowledge_scopes,
        "output_schema": ver.output_schema,
        "limits_config": ver.limits_config,
        "audit_config": ver.audit_config,
        "enterprise_config": ver.enterprise_config,
        "ui_config": ver.ui_config,
        "tags": ver.tags,
    }


def _user_in_canary_cohort(
    user_ctx: UserContext,
    release_config: dict[str, Any] | None,
) -> bool:
    """Return True if user should receive the **current** agent_apps row."""
    rc = release_config or {}
    if rc.get("strategy") != "canary":
        return True
    canary = rc.get("canary") or {}
    dept = user_ctx.department
    target_dep = canary.get("target_departments") or []
    if dept and isinstance(target_dep, list) and dept in target_dep:
        return True
    targets = canary.get("target_users") or []
    if isinstance(targets, list) and user_ctx.user_id_hash in targets:
        return True
    pct_raw = canary.get("percent", 0)
    try:
        pct = int(pct_raw)
    except (TypeError, ValueError):
        pct = 0
    pct = max(0, min(100, pct))
    if pct >= 100:
        return True
    if pct <= 0:
        return False
    digest = hashlib.sha256(
        f"{user_ctx.user_id_hash}:{rc.get('strategy', '')}".encode()
    ).hexdigest()
    bucket = int(digest, 16) % 100
    return bucket < pct


async def resolve_compiler_agent_dict(
    db: AsyncSession,
    *,
    agent_id: str,
    user_ctx: UserContext,
) -> dict[str, Any]:
    """Load ``AgentApp`` and apply ``release_config`` for compile-time snapshot."""
    q = await db.execute(select(AgentApp).where(AgentApp.id == agent_id))
    agent = q.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent not found: {agent_id}")

    rc = agent.release_config if isinstance(agent.release_config, dict) else {}
    strategy = rc.get("strategy", "full")

    if strategy == "pinned":
        pinned = rc.get("pinned_version")
        if not pinned:
            logger.warning(
                "pinned strategy without pinned_version; using live row",
                extra={"agent_id": agent_id},
            )
            return _compiler_dict_from_app_row(agent)
        qv = await db.execute(
            select(AgentVersion).where(
                AgentVersion.agent_id == agent_id,
                AgentVersion.version == str(pinned),
            )
        )
        snap = qv.scalar_one_or_none()
        if snap is None:
            raise ValueError(
                f"pinned_version {pinned} not found for agent {agent_id}"
            )
        return _compiler_dict_from_version(agent_id, snap)

    if strategy == "canary":
        if _user_in_canary_cohort(user_ctx, rc):
            return _compiler_dict_from_app_row(agent)
        q_hist = await db.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.created_at.desc())
        )
        hist = list(q_hist.scalars().all())
        if len(hist) < 2:
            return _compiler_dict_from_app_row(agent)
        stable = hist[1]
        return _compiler_dict_from_version(agent_id, stable)

    return _compiler_dict_from_app_row(agent)
