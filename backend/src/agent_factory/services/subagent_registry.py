"""Sub-agent run registry (OpenClaw subagent-registry parity)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.db.models.subagent_run import SubagentRun


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_subagent_run_id() -> str:
    return f"subrun_{uuid.uuid4().hex[:16]}"


async def register_subagent_run(
    db: AsyncSession,
    *,
    controller_session_id: str,
    child_session_id: str,
    agent_id: str,
    user_id_hash: str,
    task_name: str | None = None,
    label: str | None = None,
    description: str | None = None,
) -> SubagentRun:
    now = _utc_now()
    row = SubagentRun(
        run_id=new_subagent_run_id(),
        controller_session_id=controller_session_id,
        child_session_id=child_session_id,
        agent_id=agent_id,
        user_id_hash=user_id_hash,
        task_name=task_name,
        label=label,
        description=description,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return row


async def update_subagent_run(
    db: AsyncSession,
    run_id: str,
    **fields: Any,
) -> SubagentRun | None:
    q = await db.execute(select(SubagentRun).where(SubagentRun.run_id == run_id))
    row = q.scalar_one_or_none()
    if row is None:
        return None
    for key, val in fields.items():
        if hasattr(row, key):
            setattr(row, key, val)
    row.updated_at = _utc_now()
    await db.flush()
    return row


async def list_subagent_runs(
    db: AsyncSession,
    *,
    controller_session_id: str,
    limit: int = 50,
) -> list[SubagentRun]:
    q = await db.execute(
        select(SubagentRun)
        .where(SubagentRun.controller_session_id == controller_session_id)
        .order_by(SubagentRun.created_at.desc())
        .limit(limit)
    )
    return list(q.scalars().all())


async def find_subagent_by_task_name(
    db: AsyncSession,
    *,
    controller_session_id: str,
    task_name: str,
) -> SubagentRun | None:
    q = await db.execute(
        select(SubagentRun)
        .where(
            SubagentRun.controller_session_id == controller_session_id,
            SubagentRun.task_name == task_name,
        )
        .order_by(SubagentRun.created_at.desc())
        .limit(1)
    )
    return q.scalar_one_or_none()


async def set_yield_message(
    db: AsyncSession,
    *,
    run_id: str,
    message: str,
) -> None:
    await db.execute(
        update(SubagentRun)
        .where(SubagentRun.run_id == run_id)
        .values(yield_message=message, updated_at=_utc_now())
    )
