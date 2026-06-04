"""Skill Compiler pure functions (docs/07, docs/34)."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from agent_factory.core.enterprise_merge import merge_enterprise_configs
from agent_factory.core.permissions import intersect_retrieval_scopes, intersect_tools
from agent_factory.core.prompt_builder import (
    build_prompt_parts,
    resolve_risk_tier_prompt,
)
from agent_factory.core.script_hooks import build_script_hooks
from agent_factory.core.user_context import UserContext
from agent_factory.core.workflow_dag import build_workflow_from_enterprise

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _generate_run_id() -> str:
    now = datetime.now(UTC)
    nano = uuid.uuid4().hex[:6]
    return f"run_{now.strftime('%Y%m%d_%H%M%S')}_{nano}"


def _sorted_file_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Stable key order for hashing (prd skill_file_manifest anchor)."""
    return {k: manifest[k] for k in sorted(manifest.keys())}


def _compute_skill_package_hash(
    skill_id: str,
    skill_version: str,
    skill_body: str,
    file_manifest: dict[str, Any],
) -> str:
    """SHA-256 over canonical JSON: id, version, body, sorted file_manifest."""
    payload: dict[str, Any] = {
        "file_manifest": _sorted_file_manifest(file_manifest),
        "skill_body": skill_body,
        "skill_id": skill_id,
        "skill_version": skill_version,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_runspec_schema_version(raw: Any) -> int:
    """Read agent-declared schema version; default 1; clamp invalid to 1."""
    if raw is None:
        return 1
    try:
        v = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "invalid runspec_schema_version %r, defaulting to 1",
            raw,
        )
        return 1
    if v < 1:
        logger.warning("runspec_schema_version %s < 1, clamping to 1", v)
        return 1
    if v > 1:
        logger.info(
            "runspec_schema_version %s: P0 runner uses v1 field subset",
            v,
        )
    return v


def _resolve_output_schema(
    agent_app: dict[str, Any],
    merged_ent: dict[str, Any],
) -> str | None:
    """Agent top-level wins; else merged enterprise ``output_schema``."""
    top = agent_app.get("output_schema")
    if isinstance(top, str) and top.strip():
        return top.strip()
    ent = merged_ent.get("output_schema")
    if isinstance(ent, str) and ent.strip():
        return ent.strip()
    return None


def compile_runspec(
    *,
    agent_app: dict[str, Any],
    skill_pkg: dict[str, Any],
    platform_policy: str | None,
    org_policy: str | None,
    user_ctx: UserContext,
    available_tools: list[str],
    user_data_domains: list[str] | None = None,
    runtime_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile agent.yaml + skill + policies + user_ctx into RunSpec dict.

    When ``SCRIPT_HOOKS_ENABLED`` is false, ``script_hooks`` is ``{}`` (P0).
    """
    from agent_factory.config import get_settings

    settings = get_settings()
    agent_id = agent_app["id"]
    agent_version = agent_app.get("version", "0.1.0")
    skill_id = skill_pkg.get("id", agent_app.get("skill_config", {}).get("id", ""))
    skill_version = skill_pkg.get("version", "0.1.0")

    # Tool intersection
    agent_tools = agent_app.get("tools_allow") or []
    skill_tools = (skill_pkg.get("tools") or {}).get("require", []) + (
        skill_pkg.get("tools") or {}
    ).get("optional", [])
    merged_tools_override = skill_pkg.get("_merged_allowed_tools")
    merged_scopes_override = skill_pkg.get("_merged_retrieval_scopes")

    allowed_tools = intersect_tools(
        agent_tools=agent_tools,
        skill_tools=skill_tools,
        user_permissions=list(user_ctx.permissions) if user_ctx.permissions else None,
        department_permissions=None,  # P0: not stored in DB yet
        gateway_available=available_tools,
    )
    if isinstance(merged_tools_override, list):
        allowed_tools = intersect_tools(
            agent_tools=allowed_tools,
            skill_tools=merged_tools_override,
            user_permissions=None,
            department_permissions=None,
            gateway_available=available_tools,
        )

    # Retrieval scopes intersection
    agent_scopes = agent_app.get("knowledge_scopes") or []
    skill_scopes = (skill_pkg.get("knowledge_scopes") or {}).get("suggest", [])
    retrieval_scopes = intersect_retrieval_scopes(
        agent_scopes=agent_scopes,
        skill_scopes=skill_scopes,
        user_domains=user_data_domains,
    )
    if isinstance(merged_scopes_override, list):
        retrieval_scopes = intersect_retrieval_scopes(
            agent_scopes=retrieval_scopes,
            skill_scopes=merged_scopes_override,
            user_domains=user_data_domains,
        )

    # Prompt assembly (enterprise.yaml merged with agent enterprise block)
    skill_ent = skill_pkg.get("enterprise") or {}
    agent_ent = agent_app.get("enterprise_config") or {}
    merged_ent = merge_enterprise_configs(skill_ent, agent_ent)
    risk_tier = (
        merged_ent.get("risk_tier")
        or skill_pkg.get("risk_tier")
        or "low"
    )
    risk_tier_prompt = resolve_risk_tier_prompt(
        str(risk_tier),
        merged_enterprise=merged_ent,
        agent_enterprise=agent_ent,
    )
    prompts_raw = merged_ent.get("prompts")
    enterprise_prompts = (
        prompts_raw if isinstance(prompts_raw, list) else None
    )
    always_refs = skill_pkg.get("always_refs", [])
    lazy_refs = skill_pkg.get("lazy_refs", [])
    indexed_refs = skill_pkg.get("indexed_refs", [])

    prompt_parts = build_prompt_parts(
        platform_policy=platform_policy,
        org_policy=org_policy,
        agent_instruction=agent_app.get("instruction"),
        risk_tier_prompt=risk_tier_prompt,
        enterprise_prompts=enterprise_prompts,
        skill_body=skill_pkg.get("skill_body"),
        always_refs=always_refs,
        lazy_refs=lazy_refs,
        indexed_refs=indexed_refs,
    )

    # Runtime defaults (DB JSONB may store null → key present, value None)
    model_policy = agent_app.get("model_policy") or {}
    limits = agent_app.get("limits_config") or {}
    # Align with models.yaml defaults: avoid qwen3-32b → localhost:8000/v1 (self-call / 502).
    runtime = {
        "model": model_policy.get("default", "MiniMax-M2.7"),
        "fallback_model": model_policy.get("fallback", "MiniMax-M2.7"),
        "max_turns": limits.get("max_turns", 6),
        "timeout_seconds": limits.get("timeout_seconds", 90),
        "max_tokens": limits.get("max_tokens", 8000),
    }
    ctx_mem = limits.get("context_memory")
    if isinstance(ctx_mem, dict):
        runtime["context_memory"] = ctx_mem

    if runtime_overrides:
        for key, val in runtime_overrides.items():
            if val is not None:
                runtime[key] = val

    wf = build_workflow_from_enterprise(
        merged_ent,
        enabled=settings.WORKFLOW_DAG_ENABLED,
    )
    if wf is not None:
        runtime["workflow"] = wf
    multi_ids = skill_pkg.get("_multi_skill_ids")
    if isinstance(multi_ids, list) and multi_ids:
        runtime["multi_skill_ids"] = multi_ids

    audit_cfg = agent_app.get("audit_config") or {}
    audit = {
        "level": audit_cfg.get("level", "minimal"),
        "trace_prompt": audit_cfg.get("trace_prompt", False),
        "trace_tool_calls": audit_cfg.get("trace_tool_calls", True),
        "trace_retrieval_ids": audit_cfg.get("trace_retrieval_ids", False),
        "retain_days": audit_cfg.get("retain_days", 90),
    }

    file_manifest_raw = skill_pkg.get("file_manifest") or {}
    file_manifest: dict[str, Any] = (
        file_manifest_raw if isinstance(file_manifest_raw, dict) else {}
    )
    skill_body = str(skill_pkg.get("skill_body", ""))
    skill_hash = _compute_skill_package_hash(
        skill_id,
        skill_version,
        skill_body,
        file_manifest,
    )
    runspec_sv = _parse_runspec_schema_version(
        agent_app.get("runspec_schema_version"),
    )
    output_schema = _resolve_output_schema(agent_app, merged_ent)

    script_hooks = build_script_hooks(
        merged_ent,
        enabled=settings.SCRIPT_HOOKS_ENABLED,
    )

    return {
        "runspec_schema_version": runspec_sv,
        "run_id": _generate_run_id(),
        "agent_id": agent_id,
        "agent_version": agent_version,
        "skill_id": skill_id,
        "skill_version": skill_version,
        "skill_package_hash": skill_hash,
        "skill_file_manifest": file_manifest,
        "user_id_hash": user_ctx.user_id_hash,
        "department": user_ctx.department,
        "prompt_parts": prompt_parts,
        "lazy_references": lazy_refs,
        "indexed_references": indexed_refs,
        "allowed_tools": allowed_tools,
        "retrieval_scopes": retrieval_scopes,
        "script_hooks": script_hooks,
        "output_schema": output_schema,
        "runtime": runtime,
        "audit": audit,
    }
