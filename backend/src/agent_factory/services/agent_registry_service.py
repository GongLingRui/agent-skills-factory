"""Agent registry CRUD and version snapshots (docs/19 §Agent 管理接口)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, false as sa_false, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.core.rbac import (
    RegistryDeptScope,
    assert_registry_department_allowed,
)
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.db.models.agent_version import AgentVersion
from agent_factory.db.models.skill import Skill
from agent_factory.db.models.system import SystemConfig
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.agent_yaml import (
    normalize_agent_yaml_dict,
    validate_required_agent_fields,
)

logger = logging.getLogger(__name__)


def _scope_or_global(scope: RegistryDeptScope | None) -> RegistryDeptScope:
    return scope if scope is not None else RegistryDeptScope("global")


def _apply_department_owner_filter(
    stmt: Any,
    scope: RegistryDeptScope,
) -> Any:
    if scope.mode == "global":
        return stmt
    if scope.mode == "blocked":
        return stmt.where(sa_false())
    return stmt.where(AgentApp.owner == scope.owner_value)


async def _get_agent_for_registry_scope(
    db: AsyncSession,
    agent_id: str,
    scope: RegistryDeptScope,
) -> AgentApp:
    assert_registry_department_allowed(scope)
    if scope.mode == "global":
        q = await db.execute(select(AgentApp).where(AgentApp.id == agent_id))
    else:
        q = await db.execute(
            select(AgentApp).where(
                AgentApp.id == agent_id,
                AgentApp.owner == scope.owner_value,
            )
        )
    agent = q.scalar_one_or_none()
    if agent is None:
        raise AgentFactoryException(
            "AGENT_NOT_FOUND",
            f"Agent not found: {agent_id}",
            status_code=404,
        )
    return agent


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _max_versions_keep(db: AsyncSession) -> int:
    q = await db.execute(
        select(SystemConfig).where(SystemConfig.key == "agent.max_versions_keep")
    )
    row = q.scalar_one_or_none()
    if row is None or row.value is None:
        return 10
    raw = row.value
    if isinstance(raw, int):
        return max(1, raw)
    if isinstance(raw, str) and raw.isdigit():
        return max(1, int(raw))
    return 10


async def _ensure_skill_exists(
    db: AsyncSession,
    skill_id: str,
    version_pin: str | None,
) -> None:
    """Raise AgentFactoryException when Skill is missing."""
    if version_pin in (None, "", "latest"):
        q = await db.execute(select(Skill.id).where(Skill.id == skill_id).limit(1))
    else:
        q = await db.execute(
            select(Skill.id).where(
                Skill.id == skill_id,
                Skill.version == str(version_pin),
            )
        )
    if q.scalar_one_or_none() is None:
        raise AgentFactoryException(
            "SKILL_NOT_FOUND",
            f"Skill not found: {skill_id}@{version_pin or 'latest'}",
            status_code=404,
        )


def _apply_payload_to_agent(agent: AgentApp, payload: dict[str, Any]) -> None:
    """Assign normalized fields onto an ``AgentApp`` row."""
    agent.name = str(payload["name"])
    agent.description = payload.get("description")
    agent.instruction = payload.get("instruction")
    agent.version = str(payload["version"])
    agent.runspec_schema_version = int(payload.get("runspec_schema_version", 1))
    agent.owner = payload.get("owner")
    agent.lifecycle_state = str(payload.get("lifecycle_state", "active"))
    agent.release_config = payload.get("release_config")
    agent.model_policy = payload.get("model_policy")
    agent.skill_config = payload.get("skill_config")
    agent.tools_allow = payload.get("tools_allow")
    agent.knowledge_scopes = payload.get("knowledge_scopes")
    agent.output_schema = payload.get("output_schema")
    agent.limits_config = payload.get("limits_config")
    agent.concurrency_config = payload.get("concurrency_config")
    agent.audit_config = payload.get("audit_config")
    agent.enterprise_config = payload.get("enterprise_config")
    agent.tags = payload.get("tags")
    agent.ui_config = payload.get("ui_config")
    agent.degradation_exempt = bool(payload.get("degradation_exempt", False))
    agent.updated_at = _utc_now()


def _snapshot_from_app(agent: AgentApp, created_by: str) -> AgentVersion:
    return AgentVersion(
        agent_id=agent.id,
        version=agent.version,
        name=agent.name,
        description=agent.description,
        instruction=agent.instruction,
        release_config=agent.release_config,
        model_policy=agent.model_policy,
        skill_config=agent.skill_config,
        tools_allow=agent.tools_allow,
        knowledge_scopes=agent.knowledge_scopes,
        output_schema=agent.output_schema,
        limits_config=agent.limits_config,
        concurrency_config=agent.concurrency_config,
        audit_config=agent.audit_config,
        enterprise_config=agent.enterprise_config,
        tags=agent.tags,
        ui_config=agent.ui_config,
        created_at=_utc_now(),
        created_by=created_by,
    )


async def _upsert_version_snapshot(
    db: AsyncSession,
    agent: AgentApp,
    created_by: str,
) -> None:
    q = await db.execute(
        select(AgentVersion).where(
            AgentVersion.agent_id == agent.id,
            AgentVersion.version == agent.version,
        )
    )
    existing = q.scalar_one_or_none()
    snap = _snapshot_from_app(agent, created_by)
    if existing:
        for attr in (
            "name",
            "description",
            "instruction",
            "release_config",
            "model_policy",
            "skill_config",
            "tools_allow",
            "knowledge_scopes",
            "output_schema",
            "limits_config",
            "concurrency_config",
            "audit_config",
            "enterprise_config",
            "tags",
            "ui_config",
        ):
            setattr(existing, attr, getattr(snap, attr))
        existing.created_by = created_by
    else:
        db.add(snap)
    await db.flush()


async def _prune_versions(db: AsyncSession, agent_id: str, keep: int) -> None:
    q = await db.execute(
        select(AgentVersion.version)
        .where(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.created_at.desc())
    )
    rows = [r[0] for r in q.all()]
    if len(rows) <= keep:
        return
    for ver in rows[keep:]:
        await db.execute(
            delete(AgentVersion).where(
                AgentVersion.agent_id == agent_id,
                AgentVersion.version == ver,
            )
        )


async def register_agent(
    db: AsyncSession,
    body: dict[str, Any],
    *,
    created_by: str,
    dept_scope: RegistryDeptScope | None = None,
) -> AgentApp:
    """Create ``AgentApp`` + version snapshot."""
    payload = normalize_agent_yaml_dict(body)
    validate_required_agent_fields(payload)
    scope = _scope_or_global(dept_scope)
    assert_registry_department_allowed(scope)
    if scope.mode == "owner_eq":
        ov = payload.get("owner")
        if ov is not None and str(ov).strip() not in ("", "null"):
            if str(ov).strip() != scope.owner_value:
                raise AgentFactoryException(
                    "FORBIDDEN",
                    "owner 与当前部门不匹配",
                    status_code=403,
                )
        payload["owner"] = scope.owner_value
    aid = str(payload["id"])

    q = await db.execute(select(AgentApp).where(AgentApp.id == aid))
    if q.scalar_one_or_none() is not None:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            f"Agent already exists: {aid}",
            status_code=409,
        )

    sk = payload.get("skill_config") or {}
    await _ensure_skill_exists(
        db,
        str(sk.get("id", "")),
        str(sk.get("version_pin")) if sk.get("version_pin") else "latest",
    )

    now = _utc_now()
    agent = AgentApp(
        id=aid,
        name=str(payload["name"]),
        description=payload.get("description"),
        instruction=payload.get("instruction"),
        version=str(payload["version"]),
        runspec_schema_version=int(payload.get("runspec_schema_version", 1)),
        owner=payload.get("owner"),
        lifecycle_state=str(payload.get("lifecycle_state", "active")),
        release_config=payload.get("release_config"),
        model_policy=payload.get("model_policy"),
        skill_config=payload.get("skill_config"),
        tools_allow=payload.get("tools_allow"),
        knowledge_scopes=payload.get("knowledge_scopes"),
        output_schema=payload.get("output_schema"),
        limits_config=payload.get("limits_config"),
        concurrency_config=payload.get("concurrency_config"),
        audit_config=payload.get("audit_config"),
        enterprise_config=payload.get("enterprise_config"),
        tags=payload.get("tags"),
        ui_config=payload.get("ui_config"),
        degradation_exempt=bool(payload.get("degradation_exempt", False)),
        created_at=now,
        updated_at=now,
        created_by=created_by,
    )
    db.add(agent)
    await db.flush()

    await _upsert_version_snapshot(db, agent, created_by)
    keep = await _max_versions_keep(db)
    await _prune_versions(db, aid, keep)
    return agent


async def update_agent(
    db: AsyncSession,
    agent_id: str,
    body: dict[str, Any],
    *,
    created_by: str,
    dept_scope: RegistryDeptScope | None = None,
) -> AgentApp:
    """Replace Agent configuration and refresh version snapshot."""
    scope = _scope_or_global(dept_scope)
    agent = await _get_agent_for_registry_scope(db, agent_id, scope)

    payload = normalize_agent_yaml_dict(body)
    if str(payload["id"]) != agent_id:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "body id must match path agent_id",
            status_code=400,
        )
    validate_required_agent_fields(payload)

    if scope.mode == "owner_eq":
        payload["owner"] = scope.owner_value

    sk = payload.get("skill_config") or {}
    await _ensure_skill_exists(
        db,
        str(sk.get("id", "")),
        str(sk.get("version_pin")) if sk.get("version_pin") else "latest",
    )

    _apply_payload_to_agent(agent, payload)
    await db.flush()

    await _upsert_version_snapshot(db, agent, created_by)
    keep = await _max_versions_keep(db)
    await _prune_versions(db, agent_id, keep)
    return agent


def _normalize_tags(tags: list[Any] | None) -> list[str]:
    """Trim, dedupe, drop empty tag strings."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags or []:
        s = str(raw).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


async def patch_agent_tags(
    db: AsyncSession,
    agent_id: str,
    tags: list[Any],
    *,
    created_by: str,
    dept_scope: RegistryDeptScope | None = None,
) -> AgentApp:
    """Update only ``tags`` on an Agent and refresh version snapshot."""
    scope = _scope_or_global(dept_scope)
    agent = await _get_agent_for_registry_scope(db, agent_id, scope)
    agent.tags = _normalize_tags(tags)
    agent.updated_at = _utc_now()
    await db.flush()

    await _upsert_version_snapshot(db, agent, created_by)
    keep = await _max_versions_keep(db)
    await _prune_versions(db, agent_id, keep)
    return agent


async def list_registry_agents(
    db: AsyncSession,
    *,
    lifecycle_state: str | None = None,
    dept_scope: RegistryDeptScope | None = None,
) -> list[dict[str, Any]]:
    """全量列表（含非 active），供管理台 / 注册中心查询。"""
    scope = _scope_or_global(dept_scope)
    q = select(AgentApp).order_by(AgentApp.updated_at.desc())
    q = _apply_department_owner_filter(q, scope)
    if lifecycle_state:
        q = q.where(AgentApp.lifecycle_state == lifecycle_state)
    res = await db.execute(q)
    out: list[dict[str, Any]] = []
    for a in res.scalars().all():
        rc = a.release_config if isinstance(a.release_config, dict) else {}
        strat = "full"
        if isinstance(rc, dict) and rc.get("strategy"):
            strat = str(rc["strategy"])
        tags = a.tags if isinstance(a.tags, list) else ([] if a.tags is None else [])
        out.append(
            {
                "id": a.id,
                "name": a.name,
                "description": a.description or "",
                "version": a.version,
                "lifecycle_state": a.lifecycle_state,
                "owner": a.owner,
                "tags": tags,
                "release_strategy": strat,
                "created_at": a.created_at.isoformat() + "Z" if a.created_at else None,
                "updated_at": a.updated_at.isoformat() + "Z" if a.updated_at else None,
            },
        )
    return out


async def set_agent_lifecycle(
    db: AsyncSession,
    agent_id: str,
    lifecycle_state: str,
    *,
    dept_scope: RegistryDeptScope | None = None,
) -> AgentApp:
    """切换 ``active`` / ``cold`` / ``archived``（PRD 生命周期）。"""
    allowed = frozenset({"active", "cold", "archived"})
    if lifecycle_state not in allowed:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            f"lifecycle_state must be one of {sorted(allowed)}",
            status_code=400,
        )
    scope = _scope_or_global(dept_scope)
    agent = await _get_agent_for_registry_scope(db, agent_id, scope)
    agent.lifecycle_state = lifecycle_state
    agent.updated_at = _utc_now()
    await db.flush()
    return agent


async def archive_agent(
    db: AsyncSession,
    agent_id: str,
    *,
    dept_scope: RegistryDeptScope | None = None,
) -> None:
    scope = _scope_or_global(dept_scope)
    agent = await _get_agent_for_registry_scope(db, agent_id, scope)
    agent.lifecycle_state = "archived"
    agent.updated_at = _utc_now()
    await db.flush()


async def apply_release_strategy(
    db: AsyncSession,
    agent_id: str,
    *,
    strategy: str,
    canary: dict[str, Any] | None,
    pinned_version: str | None,
    dept_scope: RegistryDeptScope | None = None,
) -> AgentApp:
    """Merge release controls onto ``agent_apps.release_config``."""
    scope = _scope_or_global(dept_scope)
    agent = await _get_agent_for_registry_scope(db, agent_id, scope)
    rc: dict[str, Any] = {}
    if isinstance(agent.release_config, dict):
        rc = dict(agent.release_config)
    rc["strategy"] = strategy
    if canary is not None:
        rc["canary"] = canary
    if pinned_version is not None:
        rc["pinned_version"] = pinned_version
    agent.release_config = rc
    agent.updated_at = _utc_now()
    await db.flush()
    return agent


async def list_agent_versions(
    db: AsyncSession,
    agent_id: str,
    *,
    limit: int = 10,
    dept_scope: RegistryDeptScope | None = None,
) -> list[dict[str, Any]]:
    scope = _scope_or_global(dept_scope)
    await _get_agent_for_registry_scope(db, agent_id, scope)
    qv = await db.execute(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.created_at.desc())
        .limit(limit)
    )
    out: list[dict[str, Any]] = []
    for row in qv.scalars().all():
        rc = row.release_config if isinstance(row.release_config, dict) else {}
        strat = rc.get("strategy", "full")
        created = row.created_at
        out.append(
            {
                "version": row.version,
                "created_at": (
                    created.isoformat() + "Z" if created else None
                ),
                "strategy": strat,
            }
        )
    return out
