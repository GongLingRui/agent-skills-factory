"""Agent cron job scheduling (OpenClaw cron tool backend)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.db.models.agent_cron_job import AgentCronJob

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_job_id() -> str:
    return f"cron_{uuid.uuid4().hex[:16]}"


def compute_next_run(schedule: dict[str, Any], *, base: datetime | None = None) -> datetime | None:
    """Compute next run time from OpenClaw-style schedule object."""
    now = base or _utc_now()
    kind = str(schedule.get("kind") or "").strip().lower()
    if kind == "at":
        at_ms = schedule.get("atMs") or schedule.get("at_ms")
        at_str = schedule.get("at")
        if at_ms is not None:
            return datetime.fromtimestamp(float(at_ms) / 1000.0, tz=UTC).replace(tzinfo=None)
        if isinstance(at_str, str) and at_str.strip():
            try:
                return datetime.fromisoformat(at_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                return None
        return None
    if kind == "every":
        every_ms = schedule.get("everyMs") or schedule.get("every_ms") or schedule.get("every")
        if every_ms is None:
            return None
        sec = float(every_ms) / 1000.0 if float(every_ms) > 1000 else float(every_ms)
        return now + timedelta(seconds=sec)
    if kind == "cron":
        expr = str(schedule.get("expr") or schedule.get("cron") or "").strip()
        if not expr:
            return None
        try:
            itr = croniter(expr, now)
            nxt = itr.get_next(datetime)
            return nxt.replace(tzinfo=None) if hasattr(nxt, "replace") else nxt
        except Exception:
            logger.exception("Invalid cron expr: %s", expr)
            return None
    return None


async def create_cron_job(
    db: AsyncSession,
    *,
    user_id_hash: str,
    agent_id: str,
    name: str,
    schedule: dict[str, Any],
    payload: dict[str, Any],
    session_id: str | None = None,
    description: str | None = None,
    delivery: dict[str, Any] | None = None,
    enabled: bool = True,
    delete_after_run: bool = False,
) -> AgentCronJob:
    now = _utc_now()
    job = AgentCronJob(
        job_id=new_job_id(),
        user_id_hash=user_id_hash,
        agent_id=agent_id,
        session_id=session_id,
        name=name[:256],
        description=(description or "")[:512] or None,
        schedule=schedule,
        payload=payload,
        delivery=delivery,
        enabled=enabled,
        delete_after_run=delete_after_run,
        next_run_at=compute_next_run(schedule, base=now),
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    await db.flush()
    return job


async def get_cron_job(
    db: AsyncSession, job_id: str, *, user_id_hash: str
) -> AgentCronJob | None:
    q = await db.execute(
        select(AgentCronJob).where(
            AgentCronJob.job_id == job_id,
            AgentCronJob.user_id_hash == user_id_hash,
        )
    )
    return q.scalar_one_or_none()


async def list_cron_jobs(
    db: AsyncSession, *, user_id_hash: str, agent_id: str | None = None
) -> list[AgentCronJob]:
    filters = [AgentCronJob.user_id_hash == user_id_hash]
    if agent_id:
        filters.append(AgentCronJob.agent_id == agent_id)
    q = await db.execute(
        select(AgentCronJob).where(*filters).order_by(AgentCronJob.created_at.desc())
    )
    return list(q.scalars().all())


def job_to_dict(job: AgentCronJob) -> dict[str, Any]:
    return {
        "jobId": job.job_id,
        "name": job.name,
        "description": job.description,
        "agentId": job.agent_id,
        "sessionId": job.session_id,
        "schedule": job.schedule,
        "payload": job.payload,
        "delivery": job.delivery,
        "enabled": job.enabled,
        "deleteAfterRun": job.delete_after_run,
        "nextRunAt": job.next_run_at.isoformat() if job.next_run_at else None,
        "lastRunAt": job.last_run_at.isoformat() if job.last_run_at else None,
    }
