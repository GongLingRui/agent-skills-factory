"""FastAPI dependencies (DB, Redis, auth)."""

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import get_settings
from agent_factory.core.user_context import UserContext
from agent_factory.infra.db import get_db_session
from agent_factory.infra.jwt_tokens import verify_admin_panel_jwt
from agent_factory.infra.redis import get_redis
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.auth_service import resolve_user_context


def redis_dep() -> Redis:
    return get_redis()


def _synthetic_operator_user(request: Request) -> UserContext | None:
    """Map ``ADMIN_API_TOKEN`` or admin-panel JWT to a minimal UserContext."""
    s = get_settings()
    auth = request.headers.get("Authorization") or ""
    prefix = "Bearer "
    if not auth.startswith(prefix):
        return None
    token = auth[len(prefix) :].strip()
    if not token:
        return None
    expected = (s.ADMIN_API_TOKEN or "").strip()
    if expected:
        try:
            token_ok = secrets.compare_digest(token, expected)
        except (TypeError, ValueError):
            token_ok = False
        if token_ok:
            uid_h = hashlib.sha256(b"admin_api_token").hexdigest()
            return UserContext(
                session_id="operator_admin_api",
                user_id_hash=uid_h,
                department=None,
                permissions=("platform_admin",),
                allowed_agents=None,
                data_domains=None,
            )
    try:
        payload = verify_admin_panel_jwt(token, s)
    except ValueError:
        return None
    if not payload.get("af_admin"):
        return None
    raw = payload.get("permissions")
    perms: tuple[str, ...]
    if isinstance(raw, list) and raw:
        perms = tuple(str(p) for p in raw if p)
    else:
        perms = ("platform_admin",)
    sub = str(payload.get("sub") or "admin-panel")
    uid_h = hashlib.sha256(sub.encode("utf-8")).hexdigest()
    return UserContext(
        session_id="operator_admin_jwt",
        user_id_hash=uid_h,
        department=None,
        permissions=perms,
        allowed_agents=None,
        data_domains=None,
    )


async def get_current_user_or_operator(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> UserContext:
    """Cookie session, or ``ADMIN_API_TOKEN`` / admin-panel JWT (管理台只读)."""
    op = _synthetic_operator_user(request)
    if op is not None:
        return op
    s = get_settings()
    sid = request.cookies.get(s.SESSION_COOKIE_NAME)
    if not sid:
        raise AgentFactoryException(
            "SESSION_REQUIRED",
            "session cookie required",
            status_code=401,
        )
    return await resolve_user_context(
        db=db,
        redis=redis,
        settings=s,
        session_id=sid,
    )


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> UserContext:
    """Resolve UserContext from HttpOnly session cookie."""
    s = get_settings()
    sid = request.cookies.get(s.SESSION_COOKIE_NAME)
    if not sid:
        raise AgentFactoryException(
            "SESSION_REQUIRED",
            "session cookie required",
            status_code=401,
        )
    return await resolve_user_context(
        db=db,
        redis=redis,
        settings=s,
        session_id=sid,
    )
