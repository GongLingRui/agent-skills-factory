"""Execute agent cron jobs (OpenClaw cron.run backend)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.core.user_context import UserContext
from agent_factory.db.models.agent_cron_job import AgentCronJob
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.db.models.run_spec import RunSpec
from agent_factory.services.agent_cron_service import compute_next_run

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def execute_cron_job(
    db: AsyncSession,
    *,
    job: AgentCronJob,
) -> dict[str, Any]:
    payload = job.payload if isinstance(job.payload, dict) else {}
    kind = str(payload.get("kind") or "agentTurn").strip()
    message = str(
        payload.get("message") or payload.get("text") or payload.get("systemEvent") or ""
    ).strip()
    if not message:
        return {"status": "skipped", "reason": "empty payload message"}

    session_id = job.session_id
    if not session_id:
        return {"status": "skipped", "reason": "cron job has no session_id"}

    q_sess = await db.execute(
        select(ChatSession).where(ChatSession.session_id == session_id)
    )
    session = q_sess.scalar_one_or_none()
    if session is None or not session.run_id:
        return {"status": "failed", "reason": "session not found or no run_id"}

    q_rs = await db.execute(select(RunSpec).where(RunSpec.run_id == session.run_id))
    run_spec = q_rs.scalar_one_or_none()
    if run_spec is None:
        return {"status": "failed", "reason": "run_spec not found"}

    from agent_factory.services.factory import get_runner_service

    user_ctx = UserContext(
        session_id=session.session_id,
        user_id_hash=job.user_id_hash,
        department=session.department,
        permissions=tuple(session.permissions or ()),
    )
    _ = user_ctx

    if kind == "systemEvent":
        annotated = f"[Cron systemEvent: {job.name}]\n\n{message}"
    else:
        annotated = message

    runner = get_runner_service()
    result = await runner.run_turn_background(
        db=db,
        run_spec=run_spec,
        session=session,
        user_message=annotated,
        caller_permissions=frozenset(session.permissions or ()),
    )

    now = _utc_now()
    job.last_run_at = now
    job.next_run_at = compute_next_run(job.schedule, base=now)
    if job.delete_after_run:
        await db.delete(job)
    await db.flush()

    return {
        "status": "done" if not result.get("errors") else "failed",
        "output": result.get("output"),
        "errors": result.get("errors"),
    }


async def run_due_cron_jobs(db: AsyncSession) -> int:
    """Run all enabled cron jobs that are due. Returns count executed."""
    now = _utc_now()
    q = await db.execute(
        select(AgentCronJob).where(
            AgentCronJob.enabled.is_(True),
            AgentCronJob.next_run_at.isnot(None),
            AgentCronJob.next_run_at <= now,
        )
    )
    jobs = list(q.scalars().all())
    count = 0
    for job in jobs:
        try:
            await execute_cron_job(db, job=job)
            count += 1
        except Exception:
            logger.exception("cron job %s failed", job.job_id)
    return count
