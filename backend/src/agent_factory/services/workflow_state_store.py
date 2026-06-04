"""Persist workflow DAG state on RunSpec + Redis (docs/14 P3)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.db.models.run_spec import RunSpec
from agent_factory.infra.redis import get_redis

logger = logging.getLogger(__name__)


def _redis_key(run_id: str) -> str:
    return f"workflow:state:{run_id}"


def merge_workflow_state(
    runtime: dict[str, Any] | None,
    state: dict[str, Any],
) -> dict[str, Any]:
    rt = dict(runtime or {})
    wf = rt.get("workflow")
    if not isinstance(wf, dict):
        wf = {"steps": [], "state": state}
    else:
        wf = dict(wf)
        wf["state"] = state
    rt["workflow"] = wf
    return rt


async def load_workflow_runtime(
    db: AsyncSession,
    run_id: str,
    *,
    fallback_runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load runtime JSON; Redis overlay wins for ``workflow.state``."""
    rt: dict[str, Any] = dict(fallback_runtime or {})
    try:
        redis = get_redis()
        raw = await redis.get(_redis_key(run_id))
        if raw:
            st = json.loads(raw)
            if isinstance(st, dict):
                rt = merge_workflow_state(rt, st)
    except Exception:
        logger.exception("workflow redis load failed run_id=%s", run_id)
    q = await db.execute(select(RunSpec.runtime).where(RunSpec.run_id == run_id))
    row = q.scalar_one_or_none()
    if isinstance(row, dict):
        db_rt = dict(row)
        wf_db = db_rt.get("workflow")
        wf_mem = rt.get("workflow")
        if isinstance(wf_db, dict) and isinstance(wf_mem, dict):
            st_db = wf_db.get("state") if isinstance(wf_db.get("state"), dict) else {}
            st_mem = wf_mem.get("state") if isinstance(wf_mem.get("state"), dict) else {}
            merged_st = {**st_db, **st_mem}
            rt = merge_workflow_state({**db_rt, **rt}, merged_st)
        else:
            rt = {**db_rt, **rt}
    return rt


async def persist_workflow_state(
    db: AsyncSession,
    *,
    run_id: str,
    runtime: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Write workflow state to Redis + ``run_specs.runtime``."""
    rt = merge_workflow_state(runtime, state)
    try:
        redis = get_redis()
        await redis.set(
            _redis_key(run_id),
            json.dumps(state, ensure_ascii=False),
            ex=86400 * 7,
        )
    except Exception:
        logger.exception("workflow redis save failed run_id=%s", run_id)
    await db.execute(
        update(RunSpec)
        .where(RunSpec.run_id == run_id)
        .values(runtime=rt)
    )
    await db.flush()
    return rt
