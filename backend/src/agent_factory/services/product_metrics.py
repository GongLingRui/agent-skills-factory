"""Aggregated product metrics for admin dashboards (prd §10.6, docs/32)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.db.models.agent_app import AgentApp
from agent_factory.db.models.audit import AgentUsageLog, FeedbackLog
from agent_factory.db.models.chat_session import ChatSession


def _utc_day_bounds(
    start: date,
    end: date,
) -> tuple[datetime, datetime]:
    """Inclusive calendar start, exclusive end instant for ``created_at`` filters."""
    start_dt = datetime.combine(start, time.min)
    end_exclusive = datetime.combine(end + timedelta(days=1), time.min)
    return start_dt, end_exclusive


async def compute_product_metrics_summary(
    db: AsyncSession,
    *,
    start_date: date,
    end_date: date,
    mau_window_days: int,
) -> dict[str, Any]:
    """Rollups from MAU logs, sessions, registry, and feedback (no message bodies)."""
    start_dt, end_exclusive = _utc_day_bounds(start_date, end_date)

    dau_stmt = (
        select(
            AgentUsageLog.usage_date,
            func.count(func.distinct(AgentUsageLog.user_id_hash)).label("n"),
        )
        .where(
            AgentUsageLog.usage_date >= start_date,
            AgentUsageLog.usage_date <= end_date,
            AgentUsageLog.user_id_hash.isnot(None),
        )
        .group_by(AgentUsageLog.usage_date)
        .order_by(AgentUsageLog.usage_date)
    )
    dau_rows = (await db.execute(dau_stmt)).all()
    dau_by_day = [
        {"date": row.usage_date.isoformat(), "distinct_users": int(row.n or 0)}
        for row in dau_rows
        if row.usage_date
    ]

    window_start = end_date - timedelta(days=max(mau_window_days - 1, 0))
    mau_stmt = select(func.count(func.distinct(AgentUsageLog.user_id_hash))).where(
        AgentUsageLog.usage_date >= window_start,
        AgentUsageLog.usage_date <= end_date,
        AgentUsageLog.user_id_hash.isnot(None),
    )
    mau_rolling = int((await db.execute(mau_stmt)).scalar_one() or 0)

    sess_stmt = select(func.count()).select_from(ChatSession).where(
        ChatSession.created_at.isnot(None),
        ChatSession.created_at >= start_dt,
        ChatSession.created_at < end_exclusive,
    )
    new_sessions = int((await db.execute(sess_stmt)).scalar_one() or 0)

    agents_stmt = select(func.count()).select_from(AgentApp).where(
        AgentApp.created_at.isnot(None),
        AgentApp.created_at >= start_dt,
        AgentApp.created_at < end_exclusive,
    )
    new_agents = int((await db.execute(agents_stmt)).scalar_one() or 0)

    fb_stmt = (
        select(FeedbackLog.feedback, func.count())
        .where(
            FeedbackLog.timestamp.isnot(None),
            FeedbackLog.timestamp >= start_dt,
            FeedbackLog.timestamp < end_exclusive,
        )
        .group_by(FeedbackLog.feedback)
    )
    fb_rows = (await db.execute(fb_stmt)).all()
    up = down = 0
    for kind, cnt in fb_rows:
        if kind == "thumbs_up":
            up = int(cnt)
        elif kind == "thumbs_down":
            down = int(cnt)
    fb_total = up + down
    satisfaction = (up / fb_total) if fb_total else None
    participation = (fb_total / new_sessions) if new_sessions else None

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "mau_window_days": mau_window_days,
        "mau_rolling_window_start": window_start.isoformat(),
        "dau_by_day": dau_by_day,
        "mau_rolling_distinct_users": mau_rolling,
        "new_chat_sessions": new_sessions,
        "new_agents_registered": new_agents,
        "feedback": {
            "thumbs_up": up,
            "thumbs_down": down,
            "total": fb_total,
            "satisfaction_rate": satisfaction,
            "participation_vs_sessions": participation,
        },
    }
