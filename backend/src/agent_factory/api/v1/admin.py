"""Admin ops routes: degradation (docs/19-api-reference.md)."""

from datetime import UTC, datetime, date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.api.deps import get_db_session, redis_dep
from agent_factory.api.deps_admin import (
    DegradationAuth,
    MetricsAuth,
    PlatformAdminAuth,
    RegistryAuth,
    get_admin_panel_claims,
    require_admin,
    require_degradation_control,
    require_metrics_reader,
    require_platform_admin,
    require_quota_reader,
    require_registry_operator,
    require_registry_superuser,
)
from agent_factory.core.rbac import (
    ROLE_DEPARTMENT_ADMIN,
    ROLE_PLATFORM_ADMIN,
    registry_department_scope_for_user,
)
from agent_factory.core.user_context import UserContext
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.agent_disable import set_agent_disabled
from agent_factory.services.agent_registry_service import (
    list_registry_agents,
    set_agent_lifecycle,
)
from agent_factory.services.auth_service import revoke_user_sessions_for_portal
from agent_factory.services.degradation_service import DegradationService
from agent_factory.services.product_metrics import compute_product_metrics_summary
from agent_factory.services import quota_service as qsvc
from agent_factory.services import user_sync_service as usvc

router = APIRouter(prefix="/admin", tags=["admin"])


class AgentLifecycleBody(BaseModel):
    """PRD：active / cold / archived。"""

    lifecycle_state: str = Field(..., pattern="^(active|cold|archived)$")


class DegradationLevelBody(BaseModel):
    """Force global degradation tier."""

    level: int = Field(ge=0, le=5)
    reason: str = ""
    duration_minutes: int | None = Field(None, ge=1)


class SessionRevokeBody(BaseModel):
    """门户 / 运维按 user_id_hash 撤销所有活跃会话（docs/51 阶段 D）。"""

    user_id_hash: str = Field(..., min_length=16, max_length=64)


@router.get("/agents")
async def admin_list_registry_agents(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[RegistryAuth, Depends(require_registry_operator)],
    lifecycle_state: Annotated[
        str | None,
        Query(description="按生命周期过滤，不传则返回全部"),
    ] = None,
) -> dict[str, Any]:
    """注册中心全览（含 cold/archived），供运营台使用。"""
    scope = registry_department_scope_for_user(
        auth if auth != "bearer" else None
    )
    agents = await list_registry_agents(
        db, lifecycle_state=lifecycle_state, dept_scope=scope
    )
    return {"agents": agents}


@router.patch("/agents/{agent_id}/lifecycle")
async def admin_patch_agent_lifecycle(
    agent_id: str,
    body: AgentLifecycleBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[RegistryAuth, Depends(require_registry_superuser)],
) -> dict[str, str]:
    """切换生命周期（需 ``agent.admin`` 或运维 Bearer）。"""
    scope = registry_department_scope_for_user(
        auth if auth != "bearer" else None
    )
    await set_agent_lifecycle(
        db, agent_id, body.lifecycle_state, dept_scope=scope
    )
    return {
        "status": "ok",
        "agent_id": agent_id,
        "lifecycle_state": body.lifecycle_state,
    }


@router.post("/session-revocations")
async def post_session_revocations(
    body: SessionRevokeBody,
    _admin: Annotated[bool, Depends(require_admin)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> dict[str, str | int]:
    """递增用户撤销世代；门户后端在用户权限回收后调用（需 ADMIN_API_TOKEN）。"""
    gen = await revoke_user_sessions_for_portal(
        redis=redis,
        user_id_hash=body.user_id_hash.strip(),
    )
    return {"status": "ok", "revoke_generation": gen}


@router.post("/degradation/level")
async def post_degradation_level(
    body: DegradationLevelBody,
    _authorized: Annotated[DegradationAuth, Depends(require_degradation_control)],
) -> dict[str, str | int]:
    """Force a degradation level (duration is advisory for cron/automation)."""
    _ = body.duration_minutes  # P0: optional logging only
    svc = DegradationService()
    await svc.set_level(body.level, body.reason or "", from_operator=True)
    return {"status": "ok", "level": body.level}


@router.post("/degradation/recover")
async def post_degradation_recover(
    _authorized: Annotated[DegradationAuth, Depends(require_degradation_control)],
) -> dict[str, str | int]:
    """Clear forced degradation (back to normal)."""
    svc = DegradationService()
    await svc.set_level(0, "", from_operator=True)
    return {"status": "ok", "level": 0}


@router.get("/product-metrics/summary")
async def get_product_metrics_summary(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _authorized: Annotated[MetricsAuth, Depends(require_metrics_reader)],
    start_date: Annotated[date, Query(description="YYYY-MM-DD")],
    end_date: Annotated[date, Query(description="YYYY-MM-DD")],
    mau_window_days: int = Query(30, ge=1, le=365),
) -> dict[str, object]:
    """Aggregated DAU/MAU proxy, new sessions, new agents, feedback (prd §10.6)."""
    if start_date > end_date:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "start_date must be on or before end_date",
            status_code=400,
        )
    return await compute_product_metrics_summary(
        db,
        start_date=start_date,
        end_date=end_date,
        mau_window_days=mau_window_days,
    )


def _operator_id(auth: PlatformAdminAuth, request: Request) -> str:
    if auth == "bearer":
        return "bearer_admin"
    if auth == "admin_jwt":
        c = get_admin_panel_claims(request) or {}
        return str(c.get("sub") or "admin_jwt")
    return auth.user_id_hash


class AgentDisableBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=256)
    duration_minutes: int = Field(..., ge=1, le=10080)


@router.post("/agents/{agent_id}/disable")
async def post_agent_disable(
    agent_id: str,
    body: AgentDisableBody,
    request: Request,
    redis: Annotated[Redis, Depends(redis_dep)],
    auth: Annotated[PlatformAdminAuth, Depends(require_platform_admin)],
) -> dict[str, Any]:
    """运维级临时屏蔽（Redis TTL，与 lifecycle=cold 语义不同）。"""
    _ = _operator_id(auth, request)
    exp = await set_agent_disabled(
        redis,
        agent_id=agent_id.strip(),
        reason=body.reason.strip(),
        duration_minutes=body.duration_minutes,
    )
    return {
        "status": "ok",
        "agent_id": agent_id.strip(),
        "expires_at": exp.replace(tzinfo=None).isoformat() + "Z",
    }


class TokenQuotaPutBody(BaseModel):
    budget_tokens: int = Field(..., ge=0)
    effective_next_period: bool = False


@router.get("/token-quotas")
async def get_token_quotas(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[UserContext | Literal["bearer", "admin_jwt"], Depends(require_quota_reader)],
    request: Request,
    scope: str | None = None,
    scope_id: str | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    items = await qsvc.list_quotas(db, scope=scope, scope_id=scope_id, period=period)
    if isinstance(auth, UserContext):
        raw = set(auth.permissions)
        if ROLE_DEPARTMENT_ADMIN in raw and ROLE_PLATFORM_ADMIN not in raw:
            dept = (auth.department or "").strip()
            items = [
                i
                for i in items
                if (
                    i["scope"] == "department"
                    and i["scope_id"] == dept
                )
                or (
                    i["scope"] == "user"
                    and i["scope_id"] == auth.user_id_hash
                )
            ]
    return {"items": items}


@router.put("/token-quotas/{scope}/{scope_id}")
async def put_token_quota(
    scope: str,
    scope_id: str,
    body: TokenQuotaPutBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[UserContext | Literal["bearer", "admin_jwt"], Depends(require_quota_reader)],
    request: Request,
) -> dict[str, Any]:
    if isinstance(auth, UserContext):
        raw = set(auth.permissions)
        if ROLE_DEPARTMENT_ADMIN in raw and ROLE_PLATFORM_ADMIN not in raw:
            dept = (auth.department or "").strip()
            if scope != "department" or scope_id.strip() != dept:
                raise AgentFactoryException(
                    "FORBIDDEN",
                    "department_admin 只能调整本部门 department 额度",
                    status_code=403,
                )
    op = _operator_id(auth, request)
    row = await qsvc.upsert_quota_budget(
        db,
        scope=scope.strip(),
        scope_id=scope_id.strip(),
        budget_tokens=body.budget_tokens,
        effective_next_period=body.effective_next_period,
        operator_id=op,
        change_reason=None,
    )
    await db.commit()
    return row


class UserRolesPutBody(BaseModel):
    roles: list[str] = Field(default_factory=list)
    reason: str = Field("", max_length=512)


@router.get("/users")
async def get_admin_users(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[PlatformAdminAuth, Depends(require_platform_admin)],
    department: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    items, total = await usvc.list_users_page(
        db, department=department, page=page, page_size=page_size
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.put("/users/{user_id}/roles")
async def put_admin_user_roles(
    user_id: str,
    body: UserRolesPutBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[PlatformAdminAuth, Depends(require_platform_admin)],
    request: Request,
) -> dict[str, str]:
    actor = _operator_id(auth, request)
    if isinstance(auth, UserContext):
        actor_uid = auth.user_id_hash
    elif auth == "admin_jwt":
        actor_uid = str(
            (get_admin_panel_claims(request) or {}).get("sub") or "admin_jwt"
        )
    else:
        actor_uid = "bearer_operator"
    if isinstance(auth, UserContext) and user_id.strip() == auth.user_id_hash:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "不允许为自己修改角色",
            status_code=400,
        )
    await usvc.upsert_user_roles_overlay(
        db,
        user_id=user_id.strip(),
        roles=list(body.roles),
        reason=body.reason or None,
        operator_id=actor,
        actor_user_id=actor_uid,
    )
    await db.commit()
    return {"status": "ok", "user_id": user_id.strip()}


@router.get("/departments")
async def get_admin_departments(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[UserContext | Literal["bearer", "admin_jwt"], Depends(require_quota_reader)],
) -> dict[str, Any]:
    _ = auth
    depts = await usvc.list_departments_flat(db)
    return {"departments": depts}


class DirectoryUserIn(BaseModel):
    user_id: str
    name: str | None = None
    department: str | None = None
    roles: list[str] = Field(default_factory=list)


class DirectoryDeptIn(BaseModel):
    code: str
    name: str | None = None
    parent: str | None = None


class DirectorySyncBody(BaseModel):
    users: list[DirectoryUserIn] = Field(default_factory=list)
    departments: list[DirectoryDeptIn] = Field(default_factory=list)


@router.post("/directory/sync")
async def post_directory_sync(
    body: DirectorySyncBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[bool, Depends(require_admin)],
) -> dict[str, int]:
    """门户 IAM 快照写入（需 ``ADMIN_API_TOKEN``）。"""
    users_payload = [u.model_dump() for u in body.users]
    depts_payload = [d.model_dump() for d in body.departments]
    stats = await usvc.replace_directory_snapshot(
        db, users=users_payload, departments=depts_payload
    )
    await db.commit()
    return stats
