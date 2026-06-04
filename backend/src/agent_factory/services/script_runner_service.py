"""Run preprocess/postprocess hooks from RunSpec (docs/25)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.db.models.run_spec import RunSpec
from agent_factory.db.models.skill import Skill
from agent_factory.infra.minio_client import MinioClient
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.audit_service import push_audit_event
from agent_factory.services.skill_bundle_storage import (
    extract_text_from_tarball,
    get_skill_bundle_bytes,
)
from agent_factory.config import get_settings
from agent_factory.workers.script_worker import (
    resolve_script_worker_runtime,
    run_controlled_script,
)

logger = logging.getLogger(__name__)


async def _load_script_source(
    db: AsyncSession,
    *,
    skill_id: str,
    skill_version: str,
    entry: str,
) -> str:
    q = await db.execute(
        select(Skill).where(Skill.id == skill_id, Skill.version == skill_version)
    )
    row = q.scalar_one_or_none()
    if row is None:
        raise AgentFactoryException(
            "NOT_FOUND", "Skill not found for script hook", status_code=404
        )
    meta = row.package_metadata if isinstance(row.package_metadata, dict) else {}
    scripts = meta.get("script_sources")
    if isinstance(scripts, dict) and entry in scripts:
        src = scripts[entry]
        if isinstance(src, str) and src.strip():
            return src
    if row.storage_path:
        from agent_factory.config import get_settings

        settings = get_settings()
        minio = MinioClient(settings)
        tarball = await get_skill_bundle_bytes(minio, settings, row.storage_path)
        text = extract_text_from_tarball(tarball, entry)
        if text:
            return text
    raise AgentFactoryException(
        "SCRIPT_NOT_FOUND",
        f"Script entry not found: {entry}",
        status_code=404,
    )


async def run_script_hooks_phase(
    db: AsyncSession,
    *,
    run_spec: RunSpec,
    phase: str,
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute all hooks in ``phase`` (preprocess|postprocess); merge outputs."""
    hooks_raw = run_spec.script_hooks
    if not isinstance(hooks_raw, dict):
        return input_payload
    hooks = hooks_raw.get(phase)
    if not isinstance(hooks, list) or not hooks:
        return input_payload
    sid = run_spec.skill_id
    sver = run_spec.skill_version
    if not sid or not sver:
        return input_payload
    merged = dict(input_payload)
    settings = get_settings()
    for spec in hooks:
        if not isinstance(spec, dict):
            continue
        entry = str(spec.get("entry") or "").strip()
        hid = str(spec.get("id") or entry)
        if not entry:
            continue
        source = await _load_script_source(
            db, skill_id=sid, skill_version=sver, entry=entry
        )
        timeout = int(spec.get("timeout_seconds", 10))
        allow_net = bool(spec.get("network", False))
        try:
            out = run_controlled_script(
                script_source=source,
                hook_id=hid,
                input_payload=merged,
                timeout_seconds=timeout,
                allow_network=allow_net,
                worker_runtime=settings.SCRIPT_WORKER_RUNTIME,
                runsc_path=settings.SCRIPT_GVISOR_RUNSC,
                gvisor_rootless=settings.SCRIPT_GVISOR_ROOTLESS,
            )
        except RuntimeError as exc:
            await push_audit_event(
                {
                    "event_type": "script_hook_failed",
                    "run_id": run_spec.run_id,
                    "phase": phase,
                    "hook_id": hid,
                    "error": str(exc)[:500],
                }
            )
            raise AgentFactoryException(
                "SCRIPT_EXECUTION_FAILED",
                str(exc),
                status_code=500,
            ) from exc
        worker_mode = resolve_script_worker_runtime(
            settings.SCRIPT_WORKER_RUNTIME,
            runsc_path=settings.SCRIPT_GVISOR_RUNSC,
        )
        await push_audit_event(
            {
                "event_type": "script_hook_ok",
                "run_id": run_spec.run_id,
                "phase": phase,
                "hook_id": hid,
                "worker_runtime": worker_mode,
            }
        )
        if isinstance(out, dict):
            merged.update(out)
    return merged
