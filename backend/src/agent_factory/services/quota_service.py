"""Token quota read/write with history (docs/19)."""

from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Any

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.db.models.quota import TokenQuota, TokenQuotaHistory
from agent_factory.middleware.error_handler import AgentFactoryException

_VALID_SCOPES = frozenset({"platform", "department", "agent", "user"})


def _month_period_bounds(period: str) -> tuple[date, date]:
    """``YYYY-MM`` -> first / last calendar day."""
    try:
        y, m = period.split("-", 1)
        yi, mi = int(y), int(m)
        _ = date(yi, mi, 1)
    except ValueError as exc:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "period must be YYYY-MM",
            status_code=400,
        ) from exc
    last = calendar.monthrange(yi, mi)[1]
    return date(yi, mi, 1), date(yi, mi, last)


def _current_period() -> tuple[str, date, date]:
    today = date.today()
    p = f"{today.year:04d}-{today.month:02d}"
    start, end = _month_period_bounds(p)
    return p, start, end


async def list_quotas(
    db: AsyncSession,
    *,
    scope: str | None,
    scope_id: str | None,
    period: str | None,
) -> list[dict[str, Any]]:
    stmt = select(TokenQuota)
    if scope:
        if scope not in _VALID_SCOPES:
            raise AgentFactoryException(
                "INVALID_PARAMS",
                "invalid scope",
                status_code=400,
            )
        stmt = stmt.where(TokenQuota.scope == scope)
    if scope_id:
        stmt = stmt.where(TokenQuota.scope_id == scope_id.strip())
    if period:
        start, end = _month_period_bounds(period)
        stmt = stmt.where(
            and_(
                TokenQuota.period_start == start,
                TokenQuota.period_end == end,
            )
        )
    stmt = stmt.order_by(TokenQuota.scope, TokenQuota.scope_id)
    q = await db.execute(stmt)
    rows = q.scalars().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        budget = int(r.budget_tokens or 0)
        used = int(r.used_tokens or 0)
        rate = (used / budget) if budget > 0 else 0.0
        p = f"{r.period_start.year:04d}-{r.period_start.month:02d}"
        out.append(
            {
                "scope": r.scope,
                "scope_id": r.scope_id,
                "budget_tokens": budget,
                "used_tokens": used,
                "usage_rate": round(rate, 4),
                "period": p,
                "period_start": r.period_start.isoformat(),
                "period_end": r.period_end.isoformat(),
            }
        )
    return out


async def upsert_quota_budget(
    db: AsyncSession,
    *,
    scope: str,
    scope_id: str,
    budget_tokens: int,
    effective_next_period: bool,
    operator_id: str,
    change_reason: str | None,
) -> dict[str, Any]:
    if scope not in _VALID_SCOPES:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "invalid scope",
            status_code=400,
        )
    sid = scope_id.strip()
    now = datetime.utcnow()
    if effective_next_period:
        cur_p, cur_start, cur_end = _current_period()
        y, mo = cur_start.year, cur_start.month
        if mo == 12:
            n_start = date(y + 1, 1, 1)
        else:
            n_start = date(y, mo + 1, 1)
        ny, nm = n_start.year, n_start.month
        last = calendar.monthrange(ny, nm)[1]
        n_end = date(ny, nm, last)
        period_label = f"{ny:04d}-{nm:02d}"
    else:
        period_label, cur_start, cur_end = _current_period()
        n_start, n_end = cur_start, cur_end

    q = await db.execute(
        select(TokenQuota).where(
            TokenQuota.scope == scope,
            TokenQuota.scope_id == sid,
            TokenQuota.period_start == n_start,
            TokenQuota.period_end == n_end,
        )
    )
    row = q.scalar_one_or_none()
    prev_budget: int | None = None
    if row is None:
        row = TokenQuota(
            scope=scope,
            scope_id=sid,
            budget_tokens=budget_tokens,
            used_tokens=0,
            period_start=n_start,
            period_end=n_end,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        prev_budget = int(row.budget_tokens or 0)
        row.budget_tokens = budget_tokens
        row.updated_at = now
    await db.flush()

    hist = TokenQuotaHistory(
        scope=scope,
        scope_id=sid,
        previous_budget=prev_budget,
        new_budget=budget_tokens,
        change_reason=change_reason,
        effective_period=period_label,
        effective_immediately=not effective_next_period,
        operator_id=operator_id,
        timestamp=now,
        created_at=now,
    )
    db.add(hist)
    await db.flush()
    return {
        "scope": scope,
        "scope_id": sid,
        "budget_tokens": budget_tokens,
        "period": period_label,
        "period_start": n_start.isoformat(),
        "period_end": n_end.isoformat(),
        "effective_next_period": effective_next_period,
    }


async def get_quota_row_for_period(
    db: AsyncSession,
    *,
    scope: str,
    scope_id: str,
    period_start: date,
    period_end: date,
) -> TokenQuota | None:
    q = await db.execute(
        select(TokenQuota).where(
            TokenQuota.scope == scope,
            TokenQuota.scope_id == scope_id,
            TokenQuota.period_start == period_start,
            TokenQuota.period_end == period_end,
        )
    )
    return q.scalar_one_or_none()


async def check_quota_allows_estimate(
    db: AsyncSession,
    *,
    scope: str,
    scope_id: str,
    estimated_tokens: int,
) -> None:
    """Raise TOKEN_QUOTA_EXCEEDED when row exists and would exceed budget."""
    _, start, end = _current_period()
    row = await get_quota_row_for_period(
        db, scope=scope, scope_id=scope_id, period_start=start, period_end=end
    )
    if row is None:
        return
    budget = int(row.budget_tokens or 0)
    used = int(row.used_tokens or 0)
    if budget <= 0:
        return
    if used + max(0, estimated_tokens) > budget:
        raise AgentFactoryException(
            "TOKEN_QUOTA_EXCEEDED",
            "Token budget exhausted for this scope",
            status_code=429,
        )


async def increment_used_tokens(
    db: AsyncSession,
    *,
    scope: str,
    scope_id: str,
    tokens: int,
) -> None:
    """Atomically add ``tokens`` to ``used_tokens`` for current month row."""
    if tokens <= 0:
        return
    _, start, end = _current_period()
    now = datetime.utcnow()
    await db.execute(
        update(TokenQuota)
        .where(
            TokenQuota.scope == scope,
            TokenQuota.scope_id == scope_id,
            TokenQuota.period_start == start,
            TokenQuota.period_end == end,
        )
        .values(
            used_tokens=TokenQuota.used_tokens + tokens,
            updated_at=now,
        )
    )
    await db.flush()
