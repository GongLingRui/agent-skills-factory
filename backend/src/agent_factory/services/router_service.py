"""Router Agent: pick target Agent App from candidates (prd P3)."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import get_settings
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.router_llm import route_with_llm

logger = logging.getLogger(__name__)


def _route_keyword(
    *,
    user_message: str,
    agents: list[AgentApp],
    candidate_agent_ids: list[str],
    department: str | None,
) -> dict[str, Any]:
    msg = user_message.lower()
    best_id = agents[0].id
    best_score = -1.0
    for ag in agents:
        score = 0.0
        name = (ag.name or "").lower()
        instr = (ag.instruction or "").lower() if ag.instruction else ""
        if name and name in msg:
            score += 3.0
        for tok in re.findall(r"[\w\u4e00-\u9fff]{2,}", name):
            if tok in msg:
                score += 1.0
        for tok in re.findall(r"[\w\u4e00-\u9fff]{4,}", instr[:200]):
            if tok in msg:
                score += 0.5
        if department and ag.owner == department:
            score += 0.25
        if score > best_score:
            best_score = score
            best_id = ag.id
    return {
        "agent_id": best_id,
        "confidence": min(1.0, max(0.1, best_score / 5.0)),
        "router": "keyword_v1",
        "candidates": candidate_agent_ids,
    }


async def route_to_agent(
    db: AsyncSession,
    *,
    user_message: str,
    candidate_agent_ids: list[str],
    department: str | None = None,
    model_gateway: Any | None = None,
    require_api_feature: bool = True,
    prefer_llm: bool | None = None,
) -> dict[str, Any]:
    """LLM router when enabled; else keyword heuristic."""
    settings = get_settings()
    if require_api_feature and not settings.ROUTER_AGENT_ENABLED:
        raise AgentFactoryException(
            "FEATURE_DISABLED",
            "Router agent is disabled",
            status_code=403,
        )
    ids = [a.strip() for a in candidate_agent_ids if a and a.strip()]
    if not ids:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "candidate_agent_ids required",
            status_code=400,
        )
    q = await db.execute(
        select(AgentApp).where(
            AgentApp.id.in_(ids),
            AgentApp.lifecycle_state == "active",
        )
    )
    agents = list(q.scalars().all())
    if not agents:
        raise AgentFactoryException(
            "NOT_FOUND",
            "No active candidate agents",
            status_code=404,
        )

    use_llm = settings.ROUTER_USE_LLM if prefer_llm is None else prefer_llm
    if use_llm and model_gateway is not None:
        model = (settings.ROUTER_MODEL or "").strip()
        if not model:
            model = str(settings.DEGRADATION_CHAT_SMALL_MODEL or "MiniMax-M2.7")
        try:
            llm_out = await route_with_llm(
                model_gateway,
                user_message=user_message,
                agents=agents,
                model=model,
                max_tokens=settings.ROUTER_LLM_MAX_TOKENS,
            )
            if llm_out is not None:
                return llm_out
        except Exception:
            logger.exception("LLM router failed; falling back to keyword router")

    return _route_keyword(
        user_message=user_message,
        agents=agents,
        candidate_agent_ids=ids,
        department=department,
    )
