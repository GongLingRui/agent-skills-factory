"""MAU retention gate: cold lifecycle + archive (docs/21, prd §15.1)."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.db.models.audit import AgentUsageLog

logger = logging.getLogger(__name__)


def _utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _mau_threshold_for_agent(agent: AgentApp, default: int) -> int:
    raw: Any = None
    ent = agent.enterprise_config
    if isinstance(ent, dict):
        raw = ent.get("mau_threshold")
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return default


async def run_mau_retention_gate(
    db: AsyncSession,
    settings: Settings,
) -> None:
    """Mark low-MAU active agents as cold; archive long-idle cold agents."""
    if not settings.MAU_RETENTION_GATE_ENABLED:
        return

    window_start = date.today() - timedelta(days=settings.MAU_RETENTION_WINDOW_DAYS)
    stmt = (
        select(
            AgentUsageLog.agent_id,
            func.count(func.distinct(AgentUsageLog.user_id_hash)).label("mau"),
        )
        .where(
            AgentUsageLog.agent_id.isnot(None),
            AgentUsageLog.usage_date >= window_start,
        )
        .group_by(AgentUsageLog.agent_id)
    )
    result = await db.execute(stmt)
    mau_by_agent: dict[str, int] = {
        str(row.agent_id): int(row.mau or 0)
        for row in result
        if row.agent_id
    }

    q_agents = await db.execute(
        select(AgentApp).where(AgentApp.lifecycle_state == "active")
    )
    now = _utc_naive()
    default_th = settings.MAU_RETENTION_DEFAULT_THRESHOLD
    cold_count = 0
    for agent in q_agents.scalars():
        if agent.degradation_exempt:
            continue
        th = _mau_threshold_for_agent(agent, default_th)
        mau = mau_by_agent.get(agent.id, 0)
        if mau < th:
            agent.lifecycle_state = "cold"
            agent.cold_since = now
            agent.updated_at = now
            cold_count += 1
            logger.info(
                "Retention: agent %s marked cold (mau=%s < threshold=%s)",
                agent.id,
                mau,
                th,
            )

    cut = now - timedelta(days=settings.MAU_COLD_ARCHIVE_AFTER_DAYS)
    arch = await db.execute(
        update(AgentApp)
        .where(
            AgentApp.lifecycle_state == "cold",
            AgentApp.cold_since.isnot(None),
            AgentApp.cold_since < cut,
        )
        .values(lifecycle_state="archived", updated_at=now)
    )
    if arch.rowcount:
        logger.info("Retention: archived %s cold agents", arch.rowcount)
    if cold_count:
        logger.info("Retention: marked %s agents cold", cold_count)
