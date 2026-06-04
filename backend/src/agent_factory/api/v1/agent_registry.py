"""Admin Agent registry: POST/PUT/DELETE, releases, versions (docs/19)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.api.deps_admin import (
    RegistryAuth,
    require_registry_operator,
    require_registry_superuser,
)
from agent_factory.core.rbac import (
    RegistryDeptScope,
    registry_department_scope_for_user,
)
from agent_factory.infra.db import get_db_session
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.agent_registry_service import (
    apply_release_strategy,
    archive_agent,
    list_agent_versions,
    patch_agent_tags,
    register_agent,
    update_agent,
)
from agent_factory.services.app_studio_service import compose_and_register_agent
from agent_factory.services.factory import get_model_gateway

router = APIRouter()


class ReleaseBody(BaseModel):
    """Adjust rollout strategy (merged into ``release_config``)."""

    strategy: str = Field(..., pattern="^(full|canary|pinned)$")
    canary: dict[str, Any] | None = None
    pinned_version: str | None = None


def _invalid_params(message: str) -> AgentFactoryException:
    return AgentFactoryException(
        "INVALID_PARAMS",
        message,
        status_code=400,
    )


def _registry_scope(auth: RegistryAuth) -> RegistryDeptScope:
    if auth == "bearer":
        return registry_department_scope_for_user(None)
    return registry_department_scope_for_user(auth)


def _created_by(auth: RegistryAuth) -> str:
    if auth == "bearer":
        return "bearer"
    return auth.user_id_hash[:16]


class AgentTagsBody(BaseModel):
    """Replace Agent tag list (portal / registry tag editor)."""

    tags: list[str] = Field(default_factory=list)


class StudioComposeBody(BaseModel):
    """Natural-language requirements → Skill-backed Agent App."""

    requirements: str = Field(..., min_length=4, max_length=4000)
    tool_preset: str | None = Field(
        default=None,
        description="OpenClaw-style preset: minimal|coding|web|browser|agents|full",
    )
    tools_allow: list[str] | None = Field(
        default=None,
        description="Explicit tool ids or group:* (overrides preset when set)",
    )


@router.get("/studio/tool-catalog")
async def get_studio_tool_catalog(
    auth: Annotated[RegistryAuth, Depends(require_registry_operator)],
) -> dict[str, Any]:
    """OpenClaw-style tool catalog + presets for Studio UI."""
    _ = auth
    from agent_factory.core.tool_catalog import catalog_for_api

    return catalog_for_api()


@router.post("/studio/compose")
async def post_studio_compose(
    body: StudioComposeBody,
    auth: Annotated[RegistryAuth, Depends(require_registry_operator)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """根据用户需求自动匹配 Skill 并注册 Agent App（应用库「+」快捷创建）。"""
    scope = _registry_scope(auth)
    try:
        return await compose_and_register_agent(
            db,
            requirements=body.requirements,
            model_gateway=get_model_gateway(),
            created_by=_created_by(auth),
            dept_scope=scope,
            tool_preset=body.tool_preset,
            tools_allow=body.tools_allow,
        )
    except AgentFactoryException:
        raise
    except ValueError as exc:
        raise _invalid_params(str(exc)) from exc


@router.post("")
async def create_agent(
    body: Annotated[dict[str, Any], Body(...)],
    auth: Annotated[RegistryAuth, Depends(require_registry_operator)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Register Agent from agent.yaml-shaped JSON."""
    scope = _registry_scope(auth)
    try:
        agent = await register_agent(
            db,
            body,
            created_by=_created_by(auth),
            dept_scope=scope,
        )
    except ValueError as exc:
        raise _invalid_params(str(exc)) from exc
    return {"id": agent.id, "version": agent.version, "status": "created"}


@router.patch("/{agent_id}/tags")
async def patch_agent_tags_route(
    agent_id: str,
    body: AgentTagsBody,
    auth: Annotated[RegistryAuth, Depends(require_registry_operator)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Update Agent tags only (应用库标签编辑)."""
    scope = _registry_scope(auth)
    agent = await patch_agent_tags(
        db,
        agent_id,
        body.tags,
        created_by=_created_by(auth),
        dept_scope=scope,
    )
    return {"id": agent.id, "tags": agent.tags or [], "status": "updated"}


@router.put("/{agent_id}")
async def put_agent(
    agent_id: str,
    body: Annotated[dict[str, Any], Body(...)],
    auth: Annotated[RegistryAuth, Depends(require_registry_operator)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Replace Agent configuration."""
    scope = _registry_scope(auth)
    try:
        agent = await update_agent(
            db,
            agent_id,
            body,
            created_by=_created_by(auth),
            dept_scope=scope,
        )
    except ValueError as exc:
        raise _invalid_params(str(exc)) from exc
    return {"id": agent.id, "version": agent.version, "status": "updated"}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    auth: Annotated[RegistryAuth, Depends(require_registry_superuser)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    """Archive Agent (lifecycle_state → archived)."""
    scope = _registry_scope(auth)
    await archive_agent(db, agent_id, dept_scope=scope)
    return {"status": "ok"}


@router.post("/{agent_id}/releases")
async def post_release(
    agent_id: str,
    body: ReleaseBody,
    auth: Annotated[RegistryAuth, Depends(require_registry_operator)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Update release / canary configuration."""
    scope = _registry_scope(auth)
    agent = await apply_release_strategy(
        db,
        agent_id,
        strategy=body.strategy,
        canary=body.canary,
        pinned_version=body.pinned_version,
        dept_scope=scope,
    )
    return {"id": agent.id, "release_config": agent.release_config}


@router.get("/{agent_id}/versions")
async def get_versions(
    agent_id: str,
    auth: Annotated[RegistryAuth, Depends(require_registry_operator)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """List recent version snapshots (default 10)."""
    scope = _registry_scope(auth)
    versions = await list_agent_versions(
        db, agent_id, limit=10, dept_scope=scope
    )
    return {"versions": versions}
