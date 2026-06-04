"""Audit query API (P0.5 consumer); writes remain async from P0 (docs/19, docs/47)."""

import csv
import io
import json
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.api.deps import get_db_session
from agent_factory.api.deps_admin import require_audit_reader
from agent_factory.db.models.audit import AuditLog, DailyStats
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.db.models.checkpoint import Checkpoint
from agent_factory.middleware.error_handler import AgentFactoryException

router = APIRouter(prefix="/audit", tags=["audit"])

_AUDIT_EXPORT_MAX = 5000


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        v = value.replace("Z", "+00:00")
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def _audit_log_filter_conditions(
    *,
    run_id: str | None,
    session_id: str | None,
    agent_id: str | None,
    department: str | None,
    user_id_hash: str | None,
    level: str | None,
    start_time: str | None,
    end_time: str | None,
) -> list[Any]:
    """Shared filters for ``/audit/logs`` and ``/audit/logs/export``."""
    conds: list[Any] = []
    if run_id:
        conds.append(AuditLog.run_id == run_id)
    if session_id:
        conds.append(AuditLog.session_id == session_id)
    if agent_id:
        conds.append(AuditLog.agent_id == agent_id)
    if department:
        conds.append(AuditLog.department == department)
    if user_id_hash:
        conds.append(AuditLog.user_id_hash == user_id_hash)
    if level:
        conds.append(AuditLog.level == level)
    st = _parse_iso_dt(start_time)
    et = _parse_iso_dt(end_time)
    if st:
        conds.append(AuditLog.timestamp >= st)
    if et:
        conds.append(AuditLog.timestamp <= et)
    return conds


def _audit_where(conds: list[Any]) -> Any:
    return and_(*conds) if conds else true()


def _daily_stats_filter_conditions(
    *,
    start_date: date,
    end_date: date,
    agent_id: str | None,
    department: str | None,
) -> list[Any]:
    """Shared filters for ``/audit/stats/daily`` and export."""
    conds: list[Any] = [
        DailyStats.stat_date >= start_date,
        DailyStats.stat_date <= end_date,
    ]
    if agent_id:
        conds.append(DailyStats.agent_id == agent_id)
    if department:
        conds.append(DailyStats.department == department)
    return conds


def _daily_stats_csv_row(row: DailyStats) -> list[str]:
    """One CSV row for ``daily_stats`` (aligned with JSON list fields)."""

    def _cell(v: Any) -> str:
        if v is None:
            return ""
        s = str(v)
        if s and s[0] in "=+-@":
            return "'" + s
        return s

    dist = json.dumps(row.model_distribution, ensure_ascii=False) if (
        row.model_distribution
    ) else ""
    d = row.stat_date.isoformat() if row.stat_date else ""
    return [
        _cell(d),
        _cell(row.agent_id),
        _cell(row.department),
        _cell(row.request_count),
        _cell(row.error_count),
        _cell(int(row.token_input)),
        _cell(int(row.token_output)),
        _cell(row.p99_latency_ms),
        dist,
    ]


def _audit_log_to_dict(row: AuditLog) -> dict[str, Any]:
    """Apply minimal/standard/full redaction for API responses."""
    level = (row.level or "minimal").lower()
    base: dict[str, Any] = {
        "id": row.id,
        "run_id": row.run_id,
        "session_id": row.session_id,
        "timestamp": row.timestamp.isoformat() + "Z" if row.timestamp else None,
        "level": row.level,
        "user_id_hash": row.user_id_hash,
        "agent_id": row.agent_id,
        "department": row.department,
        "tool_calls": row.tool_calls,
        "token_count": row.token_count,
        "cost": row.cost,
        "error_code": row.error_code,
        "retrieval_ids": row.retrieval_ids,
    }
    if level in ("standard", "full"):
        if row.prompt_summary:
            base["prompt_summary"] = row.prompt_summary[:200]
    if level == "full":
        base["full_prompt"] = row.full_prompt
        base["full_output"] = row.full_output
    return base


def _audit_log_csv_row(row: AuditLog) -> list[str]:
    """One CSV row; redaction aligned with ``_audit_log_to_dict``."""
    lvl = (row.level or "minimal").lower()
    prompt_cell = ""
    full_p = ""
    full_o = ""
    if lvl in ("standard", "full") and row.prompt_summary:
        prompt_cell = row.prompt_summary[:200]
    if lvl == "full":
        full_p = row.full_prompt or ""
        full_o = row.full_output or ""

    def _cell(v: Any) -> str:
        if v is None:
            return ""
        s = str(v)
        if s and s[0] in "=+-@":
            return "'" + s
        return s

    tool_s = json.dumps(row.tool_calls, ensure_ascii=False) if row.tool_calls else ""
    retr_s = (
        json.dumps(row.retrieval_ids, ensure_ascii=False)
        if row.retrieval_ids
        else ""
    )
    ts = row.timestamp.isoformat() + "Z" if row.timestamp else ""
    return [
        _cell(row.id),
        _cell(row.run_id),
        _cell(row.session_id),
        _cell(ts),
        _cell(row.level),
        _cell(row.user_id_hash),
        _cell(row.agent_id),
        _cell(row.department),
        tool_s,
        _cell(row.token_count),
        _cell(row.cost),
        _cell(row.error_code),
        retr_s,
        prompt_cell,
        full_p,
        full_o,
    ]


@router.get("/logs/export")
async def export_audit_logs_csv(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _authorized: Annotated[object, Depends(require_audit_reader)],
    run_id: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
    department: str | None = None,
    user_id_hash: str | None = None,
    level: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = Query(2000, ge=1, le=_AUDIT_EXPORT_MAX),
) -> StreamingResponse:
    """Export audit rows as UTF-8 CSV (same filters as ``GET /audit/logs``)."""
    conds = _audit_log_filter_conditions(
        run_id=run_id,
        session_id=session_id,
        agent_id=agent_id,
        department=department,
        user_id_hash=user_id_hash,
        level=level,
        start_time=start_time,
        end_time=end_time,
    )
    where_clause = _audit_where(conds)
    list_stmt = (
        select(AuditLog)
        .where(where_clause)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )
    rows = (await db.execute(list_stmt)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "run_id",
            "session_id",
            "timestamp",
            "level",
            "user_id_hash",
            "agent_id",
            "department",
            "tool_calls_json",
            "token_count",
            "cost",
            "error_code",
            "retrieval_ids_json",
            "prompt_summary",
            "full_prompt",
            "full_output",
        ]
    )
    for r in rows:
        writer.writerow(_audit_log_csv_row(r))

    body = buf.getvalue().encode("utf-8-sig")
    fname = f"audit_logs_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([body]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/logs")
async def list_audit_logs(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _authorized: Annotated[object, Depends(require_audit_reader)],
    run_id: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
    department: str | None = None,
    user_id_hash: str | None = None,
    level: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Paged audit log listing."""
    conds = _audit_log_filter_conditions(
        run_id=run_id,
        session_id=session_id,
        agent_id=agent_id,
        department=department,
        user_id_hash=user_id_hash,
        level=level,
        start_time=start_time,
        end_time=end_time,
    )
    where_clause = _audit_where(conds)

    count_stmt = select(func.count()).select_from(AuditLog).where(where_clause)
    total = int((await db.execute(count_stmt)).scalar_one() or 0)

    offset = (page - 1) * page_size
    list_stmt = (
        select(AuditLog)
        .where(where_clause)
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(list_stmt)).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "logs": [_audit_log_to_dict(r) for r in rows],
    }


@router.get("/stats/daily/export")
async def export_audit_daily_stats_csv(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _authorized: Annotated[object, Depends(require_audit_reader)],
    start_date: Annotated[date, Query(description="YYYY-MM-DD")],
    end_date: Annotated[date, Query(description="YYYY-MM-DD")],
    agent_id: str | None = None,
    department: str | None = None,
    limit: int = Query(2000, ge=1, le=_AUDIT_EXPORT_MAX),
) -> StreamingResponse:
    """Export ``daily_stats`` rows as UTF-8 CSV (same filters as JSON API)."""
    conds = _daily_stats_filter_conditions(
        start_date=start_date,
        end_date=end_date,
        agent_id=agent_id,
        department=department,
    )
    where_clause = and_(*conds)
    stmt = (
        select(DailyStats)
        .where(where_clause)
        .order_by(
            DailyStats.stat_date,
            DailyStats.agent_id,
            DailyStats.department,
        )
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "date",
            "agent_id",
            "department",
            "request_count",
            "error_count",
            "token_input",
            "token_output",
            "p99_latency_ms",
            "model_distribution_json",
        ]
    )
    for r in rows:
        writer.writerow(_daily_stats_csv_row(r))

    body = buf.getvalue().encode("utf-8-sig")
    fname = (
        f"audit_daily_stats_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
    )
    return StreamingResponse(
        iter([body]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/stats/daily")
async def audit_daily_stats(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _authorized: Annotated[object, Depends(require_audit_reader)],
    start_date: Annotated[date, Query(description="YYYY-MM-DD")],
    end_date: Annotated[date, Query(description="YYYY-MM-DD")],
    agent_id: str | None = None,
    department: str | None = None,
) -> dict[str, Any]:
    """Daily aggregates from ``daily_stats`` (filled by batch jobs / workers)."""
    conds = _daily_stats_filter_conditions(
        start_date=start_date,
        end_date=end_date,
        agent_id=agent_id,
        department=department,
    )
    where_clause = and_(*conds)
    stmt = select(DailyStats).where(where_clause).order_by(DailyStats.stat_date)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "dates": [
            {
                "date": r.stat_date.isoformat() if r.stat_date else None,
                "request_count": r.request_count,
                "error_count": r.error_count,
                "token_input": int(r.token_input),
                "token_output": int(r.token_output),
                "p99_latency_ms": r.p99_latency_ms,
                "model_distribution": r.model_distribution or {},
            }
            for r in rows
        ]
    }


def _session_summary_dict(sess: ChatSession) -> dict[str, Any]:
    return {
        "session_id": sess.session_id,
        "agent_id": sess.agent_id,
        "title": sess.title or sess.label,
        "status": sess.status,
        "run_status": sess.run_status,
        "turn_count": sess.turn_count,
        "total_tokens": sess.total_tokens,
        "created_at": sess.created_at.isoformat() + "Z" if sess.created_at else None,
        "last_activity": (
            sess.last_activity.isoformat() + "Z" if sess.last_activity else None
        ),
        "run_id": sess.run_id,
    }


@router.get("/sessions")
async def list_audit_sessions(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _authorized: Annotated[object, Depends(require_audit_reader)],
    q: str | None = Query(None, description="按会话 ID、标题或 Agent 模糊搜索"),
    agent_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Paged session listing for admin trace browser (no message bodies)."""
    conds: list[Any] = []
    if agent_id:
        conds.append(ChatSession.agent_id == agent_id)
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        conds.append(
            (ChatSession.session_id.ilike(like))
            | (ChatSession.title.ilike(like))
            | (ChatSession.label.ilike(like))
            | (ChatSession.agent_id.ilike(like))
        )
    where_clause = and_(*conds) if conds else true()

    count_stmt = select(func.count()).select_from(ChatSession).where(where_clause)
    total = int((await db.execute(count_stmt)).scalar_one() or 0)

    offset = (page - 1) * page_size
    list_stmt = (
        select(ChatSession)
        .where(where_clause)
        .order_by(
            ChatSession.last_activity.desc().nullslast(),
            ChatSession.created_at.desc().nullslast(),
        )
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(list_stmt)).scalars().all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "sessions": [_session_summary_dict(r) for r in rows],
    }


@router.get("/sessions/{session_id}/trace")
async def session_trace(
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _authorized: Annotated[object, Depends(require_audit_reader)],
) -> dict[str, Any]:
    """Checkpoint timeline for a session."""
    q_sess = await db.execute(
        select(ChatSession).where(ChatSession.session_id == session_id)
    )
    sess = q_sess.scalar_one_or_none()
    if sess is None:
        raise AgentFactoryException(
            "SESSION_NOT_FOUND",
            "Session not found",
            status_code=404,
        )
    run_id = sess.run_id
    q_cp = await db.execute(
        select(Checkpoint)
        .where(Checkpoint.session_id == session_id)
        .order_by(Checkpoint.turn_number)
    )
    cps = q_cp.scalars().all()
    checkpoints: list[dict[str, Any]] = []
    for c in cps:
        checkpoints.append(
            {
                "checkpoint_id": c.checkpoint_id,
                "turn_number": c.turn_number,
                "timestamp": c.timestamp.isoformat() + "Z" if c.timestamp else None,
                "token_count": c.token_count,
                "tool_calls_so_far": c.tool_calls_so_far or [],
            }
        )
    return {
        "session_id": session_id,
        "run_id": run_id,
        "checkpoints": checkpoints,
    }
