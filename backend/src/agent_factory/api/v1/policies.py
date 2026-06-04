"""Policy Registry HTTP API (docs/19)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.api.deps import get_db_session, redis_dep
from agent_factory.api.deps_admin import (
    RegistryAuth,
    admin_operator_token_matches,
)
from agent_factory.core.rbac import (
    PERM_POLICY_ADMIN,
    ROLE_DEPARTMENT_ADMIN,
    ROLE_PLATFORM_ADMIN,
    effective_permissions,
    has_any_permission,
)
from agent_factory.core.user_context import UserContext
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services import policy_service as psvc

router = APIRouter(prefix="/policies", tags=["policies"])


def _admin_bearer(request: Request) -> bool:
    return admin_operator_token_matches(request)


async def _session_user(request: Request, db: AsyncSession, redis: Any) -> UserContext:
    from agent_factory.api.deps_admin import _require_session_user

    return await _require_session_user(request, db, redis)


async def _require_policy_platform_read(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Any, Depends(redis_dep)],
) -> RegistryAuth:
    if _admin_bearer(request):
        return "bearer"
    user = await _session_user(request, db, redis)
    raw = set(user.permissions)
    if ROLE_PLATFORM_ADMIN in raw or ROLE_DEPARTMENT_ADMIN in raw:
        return user
    from agent_factory.config import get_settings

    eff = effective_permissions(
        user.permissions,
        legacy_agent_admin_implies_full=get_settings().RBAC_LEGACY_AGENT_ADMIN_IMPLIES_FULL,
    )
    if has_any_permission(eff, PERM_POLICY_ADMIN):
        return user
    raise AgentFactoryException(
        "FORBIDDEN",
        "需要 platform_admin、department_admin 或 policy 管理权限",
        status_code=403,
    )


async def _require_platform_admin_or_bearer(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Any, Depends(redis_dep)],
) -> RegistryAuth:
    if _admin_bearer(request):
        return "bearer"
    user = await _session_user(request, db, redis)
    if ROLE_PLATFORM_ADMIN not in set(user.permissions):
        raise AgentFactoryException(
            "FORBIDDEN",
            "需要 platform_admin 或运维 Bearer",
            status_code=403,
        )
    return user


async def _ensure_org_policy_write(
    request: Request,
    db: AsyncSession,
    redis: Any,
    department: str,
) -> RegistryAuth:
    if _admin_bearer(request):
        return "bearer"
    user = await _session_user(request, db, redis)
    raw = set(user.permissions)
    if ROLE_PLATFORM_ADMIN in raw:
        return user
    if ROLE_DEPARTMENT_ADMIN in raw:
        if (user.department or "").strip() != department.strip():
            raise AgentFactoryException(
                "FORBIDDEN",
                "department_admin 只能维护本部门策略",
                status_code=403,
            )
        return user
    raise AgentFactoryException(
        "FORBIDDEN",
        "需要 platform_admin、本部门 department_admin 或运维 Bearer",
        status_code=403,
    )


class PlatformPolicyBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=32)
    prompt: str = Field(..., min_length=1)
    enabled: bool = True


class OrgPolicyBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=32)
    department: str = Field(..., min_length=1, max_length=64)
    prompt: str = Field(..., min_length=1)
    enabled: bool = True


@router.get("/platform")
async def get_platform_policies(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[RegistryAuth, Depends(_require_policy_platform_read)],
) -> dict[str, Any]:
    policies = await psvc.list_platform_policies(db)
    return {"policies": policies}


@router.post("/platform")
async def post_platform_policy(
    body: PlatformPolicyBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[RegistryAuth, Depends(_require_platform_admin_or_bearer)],
) -> dict[str, Any]:
    row = await psvc.create_platform_policy_version(
        db,
        lineage_id=body.id.strip(),
        prompt=body.prompt,
        enabled=body.enabled,
    )
    await db.commit()
    return row


@router.put("/platform/{policy_id}")
async def put_platform_policy(
    policy_id: str,
    body: PlatformPolicyBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[RegistryAuth, Depends(_require_platform_admin_or_bearer)],
) -> dict[str, Any]:
    if body.id.strip() != policy_id.strip():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Body id must match path policy_id",
            status_code=400,
        )
    row = await psvc.create_platform_policy_version(
        db,
        lineage_id=policy_id.strip(),
        prompt=body.prompt,
        enabled=body.enabled,
    )
    await db.commit()
    return row


@router.get("/org/{department}")
async def get_org_policies(
    department: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[RegistryAuth, Depends(_require_policy_platform_read)],
) -> dict[str, Any]:
    if auth != "bearer":
        user = auth
        raw = set(user.permissions)
        if (
            ROLE_DEPARTMENT_ADMIN in raw
            and ROLE_PLATFORM_ADMIN not in raw
            and (user.department or "").strip() != department.strip()
        ):
            raise AgentFactoryException(
                "FORBIDDEN",
                "department_admin 只能查看本部门策略",
                status_code=403,
            )
    policies = await psvc.list_org_policies(db, department.strip())
    return {"department": department.strip(), "policies": policies}


@router.post("/org")
async def post_org_policy(
    body: OrgPolicyBody,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Any, Depends(redis_dep)],
) -> dict[str, Any]:
    dept = body.department.strip()
    await _ensure_org_policy_write(request, db, redis, dept)
    row = await psvc.create_org_policy_version(
        db,
        lineage_id=body.id.strip(),
        department=dept,
        prompt=body.prompt,
        enabled=body.enabled,
    )
    await db.commit()
    return row


@router.put("/org/{policy_id}")
async def put_org_policy(
    policy_id: str,
    body: OrgPolicyBody,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Any, Depends(redis_dep)],
) -> dict[str, Any]:
    dept = body.department.strip()
    if body.id.strip() != policy_id.strip():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Body id must match path policy_id",
            status_code=400,
        )
    await psvc.assert_org_lineage_department(
        db, lineage_id=policy_id.strip(), department=dept
    )
    await _ensure_org_policy_write(request, db, redis, dept)
    row = await psvc.create_org_policy_version(
        db,
        lineage_id=policy_id.strip(),
        department=dept,
        prompt=body.prompt,
        enabled=body.enabled,
    )
    await db.commit()
    return row
