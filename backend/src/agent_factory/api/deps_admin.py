"""Admin / registry guards: Bearer token and/or session RBAC (docs/19, docs/51)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.api.deps import redis_dep
from agent_factory.config import Settings, get_settings
from agent_factory.core.rbac import (
    PERM_AGENT_ADMIN,
    PERM_AGENT_WRITE,
    PERM_AUDIT_READ,
    PERM_DEGRADATION_CONTROL,
    PERM_SKILL_PUBLISH,
    PERM_TOOL_ADMIN,
    ROLE_DEPARTMENT_ADMIN,
    ROLE_PLATFORM_ADMIN,
    can_view_product_metrics,
    effective_permissions,
    has_any_permission,
)
from agent_factory.core.user_context import UserContext
from agent_factory.infra.db import get_db_session
from agent_factory.infra.jwt_tokens import verify_admin_panel_jwt
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.auth_service import resolve_user_context

RegistryAuth = UserContext | Literal["bearer"]
AuditAuth = UserContext | Literal["bearer_admin"]
MetricsAuth = UserContext | Literal["bearer_admin"]
DegradationAuth = UserContext | Literal["bearer_admin"]
PlatformAdminAuth = UserContext | Literal["bearer", "admin_jwt"]
SessionOrOperatorAuth = UserContext | Literal["operator"]


def _admin_bearer_token_matches(request: Request) -> bool:
    """``Authorization: Bearer <ADMIN_API_TOKEN>`` for automation."""
    s = get_settings()
    expected = (s.ADMIN_API_TOKEN or "").strip()
    if not expected:
        return False
    auth = request.headers.get("Authorization") or ""
    prefix = "Bearer "
    got = auth[len(prefix) :].strip() if auth.startswith(prefix) else ""
    return got == expected


def _eff(user: UserContext, settings: Settings) -> frozenset[str]:
    return effective_permissions(
        user.permissions,
        legacy_agent_admin_implies_full=settings.RBAC_LEGACY_AGENT_ADMIN_IMPLIES_FULL,
    )


async def require_session_or_admin_operator(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> SessionOrOperatorAuth:
    """Skill/Tool 目录只读：门户 Cookie 会话，或运维/管理面板 Bearer（与前端 adminCatalog 对齐）。"""
    if admin_operator_token_matches(request):
        return "operator"
    return await _require_session_user(request, db, redis)


async def _require_session_user(
    request: Request,
    db: AsyncSession,
    redis: Redis,
) -> UserContext:
    s = get_settings()
    sid = request.cookies.get(s.SESSION_COOKIE_NAME)
    if not sid:
        raise AgentFactoryException(
            "SESSION_REQUIRED",
            "需要登录会话，或在请求头携带 Bearer 运维令牌",
            status_code=401,
        )
    return await resolve_user_context(
        db=db,
        redis=redis,
        settings=s,
        session_id=sid,
    )


async def require_admin(request: Request) -> bool:
    """Strict Bearer-only admin (scripts); prefer granular deps for new routes."""
    s = get_settings()
    expected = (s.ADMIN_API_TOKEN or "").strip()
    if not expected:
        raise AgentFactoryException(
            "ADMIN_DISABLED",
            "Admin API token not configured (set ADMIN_API_TOKEN)",
            status_code=503,
        )
    if not _admin_bearer_token_matches(request):
        raise AgentFactoryException(
            "FORBIDDEN",
            "Invalid or missing admin token",
            status_code=403,
        )
    return True


async def require_registry_operator(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> RegistryAuth:
    """Agent 注册中心写：Bearer，或 ``agent.write`` / ``agent.admin``（含角色展开）。"""
    if _admin_bearer_token_matches(request):
        return "bearer"
    user = await _require_session_user(request, db, redis)
    eff = _eff(user, get_settings())
    if not has_any_permission(eff, PERM_AGENT_WRITE, PERM_AGENT_ADMIN):
        raise AgentFactoryException(
            "FORBIDDEN",
            "需要权限 agent.write 或 agent.admin（或运维 Bearer）",
            status_code=403,
        )
    return user


async def require_registry_superuser(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> RegistryAuth:
    """下架 / 生命周期 / Skill 下架：Bearer，或 ``agent.admin``。"""
    if _admin_bearer_token_matches(request):
        return "bearer"
    user = await _require_session_user(request, db, redis)
    eff = _eff(user, get_settings())
    if not has_any_permission(eff, PERM_AGENT_ADMIN):
        raise AgentFactoryException(
            "FORBIDDEN",
            "需要权限 agent.admin（或运维 Bearer）",
            status_code=403,
        )
    return user


async def require_skill_publish(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> RegistryAuth:
    """Skill 注册/更新：Bearer 或 ``skill.publish``（``platform_admin`` 展开含此码）。"""
    if _admin_bearer_token_matches(request):
        return "bearer"
    user = await _require_session_user(request, db, redis)
    eff = _eff(user, get_settings())
    if not has_any_permission(eff, PERM_SKILL_PUBLISH):
        raise AgentFactoryException(
            "FORBIDDEN",
            "需要权限 skill.publish（或 platform_admin / 运维 Bearer，见 docs/51）",
            status_code=403,
        )
    return user


async def require_tool_admin(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> RegistryAuth:
    """Tool 注册/更新：Bearer 或 ``tool.admin``。"""
    if _admin_bearer_token_matches(request):
        return "bearer"
    user = await _require_session_user(request, db, redis)
    eff = _eff(user, get_settings())
    if not has_any_permission(eff, PERM_TOOL_ADMIN):
        raise AgentFactoryException(
            "FORBIDDEN",
            "需要权限 tool.admin（或运维 Bearer，见 docs/51）",
            status_code=403,
        )
    return user


async def require_audit_reader(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> AuditAuth:
    """审计只读：运维 Bearer 或 ``audit.read`` / ``auditor`` / ``platform_admin``。"""
    s = get_settings()
    if admin_operator_token_matches(request):
        return "bearer_admin"
    user = await _require_session_user(request, db, redis)
    eff = _eff(user, s)
    if not has_any_permission(eff, PERM_AUDIT_READ):
        raise AgentFactoryException(
            "FORBIDDEN",
            "需要权限 audit.read，或配置 ADMIN_API_TOKEN 后使用 Bearer（docs/51）",
            status_code=403,
        )
    return user


async def require_degradation_control(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> DegradationAuth:
    """手动降级：运维 Bearer 或 ``degradation.control``。"""
    s = get_settings()
    if admin_operator_token_matches(request):
        return "bearer_admin"
    user = await _require_session_user(request, db, redis)
    eff = _eff(user, s)
    if not has_any_permission(eff, PERM_DEGRADATION_CONTROL):
        raise AgentFactoryException(
            "FORBIDDEN",
            "需要权限 degradation.control，或 ADMIN_API_TOKEN Bearer（docs/51）",
            status_code=403,
        )
    return user


async def require_metrics_reader(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> MetricsAuth:
    """产品指标摘要：运维 Bearer 或运营/管理类会话（docs/33）。"""
    s = get_settings()
    if admin_operator_token_matches(request):
        return "bearer_admin"
    user = await _require_session_user(request, db, redis)
    eff = _eff(user, s)
    if not can_view_product_metrics(eff, user.permissions):
        raise AgentFactoryException(
            "FORBIDDEN",
            "需要 platform_admin / department_admin 或 agent.admin 等（见 docs/51）",
            status_code=403,
        )
    return user


def _admin_panel_jwt_payload(request: Request) -> dict | None:
    auth = request.headers.get("Authorization") or ""
    prefix = "Bearer "
    if not auth.startswith(prefix):
        return None
    tok = auth[len(prefix) :].strip()
    if not tok:
        return None
    try:
        return verify_admin_panel_jwt(tok, get_settings())
    except ValueError:
        return None


def admin_operator_token_matches(request: Request) -> bool:
    """``ADMIN_API_TOKEN`` or valid admin-panel JWT (docs/19)."""
    if _admin_bearer_token_matches(request):
        return True
    p = _admin_panel_jwt_payload(request)
    return bool(p and p.get("af_admin"))


async def require_platform_admin(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> PlatformAdminAuth:
    """``platform_admin`` session, ``ADMIN_API_TOKEN``, or admin JWT."""
    if _admin_bearer_token_matches(request):
        return "bearer"
    p = _admin_panel_jwt_payload(request)
    if p and p.get("af_admin"):
        perms = p.get("permissions") or []
        if isinstance(perms, list) and "platform_admin" in perms:
            return "admin_jwt"
    user = await _require_session_user(request, db, redis)
    if ROLE_PLATFORM_ADMIN in set(user.permissions):
        return user
    raise AgentFactoryException(
        "FORBIDDEN",
        "需要 platform_admin、ADMIN_API_TOKEN 或含 platform_admin 的管理 JWT",
        status_code=403,
    )


async def require_quota_reader(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> UserContext | Literal["bearer", "admin_jwt"]:
    """Token quota list: platform / department admins + admin tokens."""
    if _admin_bearer_token_matches(request):
        return "bearer"
    p = _admin_panel_jwt_payload(request)
    if p and p.get("af_admin"):
        perms = p.get("permissions") or []
        if isinstance(perms, list) and "platform_admin" in perms:
            return "admin_jwt"
    user = await _require_session_user(request, db, redis)
    raw = set(user.permissions)
    if ROLE_PLATFORM_ADMIN in raw or ROLE_DEPARTMENT_ADMIN in raw:
        return user
    raise AgentFactoryException(
        "FORBIDDEN",
        "需要 platform_admin / department_admin 或运维令牌",
        status_code=403,
    )


def get_admin_panel_claims(request: Request) -> dict | None:
    """Decoded admin JWT when present and valid."""
    return _admin_panel_jwt_payload(request)
