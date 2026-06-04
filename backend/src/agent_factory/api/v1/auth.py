"""POST /auth/exchange | /auth/session | /auth/heartbeat."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.api.deps import get_current_user_or_operator
from agent_factory.api.deps_admin import require_admin
from agent_factory.config import get_settings
from agent_factory.core.rbac import can_view_product_metrics, effective_permissions
from agent_factory.core.user_context import UserContext
from agent_factory.infra.db import get_db_session
from agent_factory.infra.redis import get_redis
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.auth_service import (
    _same_site_cookie,
    bootstrap_dev_widget_session,
    consume_short_token_create_session,
    exchange_portal_token,
    heartbeat_session,
    sync_session_permissions_from_portal,
)

router = APIRouter()


class ExchangeBody(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=64)


class SessionBody(BaseModel):
    token: str = Field(..., min_length=20)


class DevSessionBody(BaseModel):
    """Local development only (requires DEV_WIDGET_AUTH_BYPASS)."""

    agent_id: str = Field(..., min_length=1, max_length=64)


def _cookie_params() -> dict:
    s = get_settings()
    return {
        "key": s.SESSION_COOKIE_NAME,
        "httponly": True,
        "secure": s.SESSION_COOKIE_SECURE,
        "samesite": _same_site_cookie(s.SESSION_COOKIE_SAMESITE),
        "max_age": s.SESSION_COOKIE_MAX_AGE,
        "path": "/",
    }


@router.post("/exchange")
async def post_exchange(
    body: ExchangeBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Portal backend exchanges portal-JWT for short-lived widget JWT."""
    if not authorization:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Authorization header required",
            status_code=400,
        )
    s = get_settings()
    return await exchange_portal_token(
        db=db,
        settings=s,
        portal_authorization=authorization,
        agent_id=body.agent_id,
    )


@router.post("/session")
async def post_session(
    body: SessionBody,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict:
    """Widget exchanges short-lived JWT for HttpOnly session cookie."""
    s = get_settings()
    row = await consume_short_token_create_session(
        db=db,
        redis=redis,
        settings=s,
        token=body.token,
    )
    cp = _cookie_params()
    response.set_cookie(value=row.session_id, **cp)
    return {"status": "ok", "session_id": row.session_id}


@router.post("/dev/session")
async def post_dev_session(
    body: DevSessionBody,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, str]:
    """Bypass portal JWT in development (docs/35); disabled in production."""
    s = get_settings()
    row = await bootstrap_dev_widget_session(
        db=db,
        redis=redis,
        settings=s,
        agent_id=body.agent_id,
    )
    cp = _cookie_params()
    response.set_cookie(value=row.session_id, **cp)
    return {"status": "ok", "session_id": row.session_id}


@router.get("/me")
async def get_me(
    user: Annotated[UserContext, Depends(get_current_user_or_operator)],
) -> dict:
    """Non-PII session hints for Chat Widget header (prd.md §4.5.4)."""
    s = get_settings()
    eff = effective_permissions(
        user.permissions,
        legacy_agent_admin_implies_full=s.RBAC_LEGACY_AGENT_ADMIN_IMPLIES_FULL,
    )
    h = user.user_id_hash
    tail = h[-6:] if len(h) >= 6 else h
    return {
        "user_id_hint": f"…{tail}",
        "department": user.department or "",
        # SHA-256 hex from portal user id (auth_service.hash_user_id); optional
        # IndexedDB SubtleCrypto key derivation (docs/11-chat-widget.md).
        "user_id_hash": h,
        "permissions": list(user.permissions),
        "effective_permissions": sorted(eff),
        "can_view_product_metrics": can_view_product_metrics(
            eff, user.permissions
        ),
        "rbac": {
            "permission_cache_seconds": s.RBAC_PERMISSION_CACHE_SECONDS,
        },
    }


@router.post("/sync-permissions")
async def post_sync_permissions(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """携带门户 JWT 刷新 Cookie 会话中的 permissions（docs/51 阶段 D）。"""
    s = get_settings()
    sid = request.cookies.get(s.SESSION_COOKIE_NAME)
    if not sid:
        raise AgentFactoryException(
            "SESSION_REQUIRED",
            "session cookie required",
            status_code=401,
        )
    if not authorization:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Authorization Bearer portal JWT required",
            status_code=400,
        )
    return await sync_session_permissions_from_portal(
        db=db,
        redis=redis,
        settings=s,
        session_id=sid,
        portal_authorization=authorization,
    )


@router.post("/heartbeat")
async def post_heartbeat(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict:
    """Extend session TTL (docs/19)."""
    s = get_settings()
    sid = request.cookies.get(s.SESSION_COOKIE_NAME)
    if not sid:
        raise AgentFactoryException(
            "SESSION_REQUIRED",
            "session cookie missing",
            status_code=401,
        )
    await heartbeat_session(db=db, redis=redis, settings=s, session_id=sid)
    cp = _cookie_params()
    response.set_cookie(value=sid, **cp)
    return {"status": "ok"}


class AdminLoginBody(BaseModel):
    """Exchange ``ADMIN_API_TOKEN`` for long-lived admin panel JWT."""

    subject: str = Field(default="admin-panel", max_length=128)
    permissions: list[str] = Field(
        default_factory=lambda: ["platform_admin"],
        description="Embedded in JWT for management APIs",
    )


@router.post("/admin-login")
async def post_admin_login(
    body: AdminLoginBody,
    _authorized: Annotated[bool, Depends(require_admin)],
) -> dict[str, Any]:
    """独立管理 JWT（docs/19）；需 ``Authorization: Bearer <ADMIN_API_TOKEN>``。"""
    from agent_factory.infra.jwt_tokens import issue_admin_panel_jwt

    s = get_settings()
    token, exp = issue_admin_panel_jwt(
        settings=s,
        subject=body.subject.strip(),
        permissions=list(body.permissions),
    )
    return {"token": token, "expires_at": exp, "token_type": "Bearer"}
