"""Portal exchange, short-lived JWT, session cookie (docs/06, docs/19)."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings
from agent_factory.core.user_context import UserContext
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.infra.jwt_tokens import (
    decode_short_lived_jwt,
    issue_short_lived_jwt,
    verify_portal_jwt,
)
from agent_factory.middleware.error_handler import AgentFactoryException


def _utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hash_user_id(raw_user_id: str, salt: str) -> str:
    """SHA-256(user_id + salt) hex digest (docs/17)."""
    body = f"{raw_user_id}:{salt}".encode()
    return hashlib.sha256(body).hexdigest()


def _redis_jti_key(jti: str) -> str:
    return f"jti_used:{jti}"


def _redis_sess_key(session_id: str) -> str:
    return f"sess:{session_id}"


def _redis_revoke_gen_key(user_id_hash: str) -> str:
    """Portal / 运维撤销会话世代（docs/51 阶段 D）。"""
    return f"sess_revoke_gen:{user_id_hash}"


async def fetch_revoke_gen_snapshot(redis: Redis, user_id_hash: str) -> int:
    raw = await redis.get(_redis_revoke_gen_key(user_id_hash))
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


async def revoke_user_sessions_for_portal(
    *,
    redis: Redis,
    user_id_hash: str,
) -> int:
    """递增撤销世代；该用户所有未换发会话在下次 resolve 时失效。"""
    return int(await redis.incr(_redis_revoke_gen_key(user_id_hash)))


def _same_site_cookie(value: str) -> str:
    m = value.strip().lower()
    if m in ("strict", "lax", "none"):
        return m
    return "strict"


async def _load_agent(db: AsyncSession, agent_id: str) -> AgentApp | None:
    q = await db.execute(select(AgentApp).where(AgentApp.id == agent_id))
    return q.scalar_one_or_none()


async def assert_user_may_access_agent(
    db: AsyncSession,
    portal_claims: dict[str, Any],
    agent_id: str,
) -> AgentApp:
    row = await _load_agent(db, agent_id)
    if row is None:
        raise AgentFactoryException(
            "AGENT_NOT_FOUND",
            f"Agent not found: {agent_id}",
            status_code=404,
        )
    if row.lifecycle_state != "active":
        raise AgentFactoryException(
            "AGENT_INACTIVE",
            "Agent is not active",
            status_code=403,
        )
    allowed = portal_claims.get("allowed_agents")
    if isinstance(allowed, Sequence) and not isinstance(allowed, (str, bytes)):
        if agent_id not in list(allowed):
            raise AgentFactoryException(
                "FORBIDDEN",
                "User cannot access this agent",
                status_code=403,
            )
    return row


def normalized_portal_allowed_agents(portal_claims: dict[str, Any]) -> list[str] | None:
    """Portal ``allowed_agents`` claim: list of agent ids, or absent = no list."""
    raw = portal_claims.get("allowed_agents")
    if raw is None:
        return None
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return [str(x) for x in raw]
    return None


def normalized_portal_data_domains(
    portal_claims: dict[str, Any],
) -> list[str] | None:
    """Portal ``data_domains`` for retrieval intersection (docs/07).

    Returns ``None`` if the claim is absent or invalid. A present claim may
    yield an empty list (explicit no domains).
    """
    if "data_domains" not in portal_claims:
        return None
    raw = portal_claims.get("data_domains")
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return None


def _allowed_tuple_from_claims(claims: dict[str, Any]) -> list[str] | None:
    """Short-lived JWT may carry ``allowed_agents`` (mirrors portal)."""
    raw = claims.get("allowed_agents")
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(x) for x in raw if isinstance(x, str)]
    return None


def _user_allowed_tuple(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return tuple(str(x) for x in value)
    return None


def _user_data_domains_tuple(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return tuple(str(x) for x in value)
    return None


async def exchange_portal_token(
    *,
    db: AsyncSession,
    settings: Settings,
    portal_authorization: str,
    agent_id: str,
) -> dict[str, Any]:
    """POST /auth/exchange body handler."""
    if not portal_authorization.lower().startswith("bearer "):
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Authorization Bearer portal JWT required",
            status_code=400,
        )
    raw = portal_authorization.split(" ", 1)[1].strip()
    try:
        claims = verify_portal_jwt(raw, settings)
    except ValueError as exc:
        msg = str(exc)
        status = 400 if "not configured" in msg else 401
        raise AgentFactoryException(
            "INVALID_PARAMS",
            msg,
            status_code=status,
        ) from exc

    sub = str(claims.get("sub") or "")
    if not sub:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Portal JWT missing sub",
            status_code=400,
        )
    await assert_user_may_access_agent(db, claims, agent_id)

    department = claims.get("department")
    if department is not None:
        department = str(department)
    perms = claims.get("permissions")
    if isinstance(perms, list):
        perm_list = [str(p) for p in perms]
    else:
        perm_list = []

    portal_allowed = normalized_portal_allowed_agents(claims)
    portal_domains = normalized_portal_data_domains(claims)
    token, exp, _jti = issue_short_lived_jwt(
        settings=settings,
        sub=sub,
        department=department,
        agent_id=agent_id,
        permissions=perm_list,
        allowed_agents=portal_allowed,
        data_domains=portal_domains,
    )
    return {"token": token, "expires_at": exp, "agent_id": agent_id}


async def consume_short_token_create_session(
    *,
    db: AsyncSession,
    redis: Redis,
    settings: Settings,
    token: str,
) -> ChatSession:
    """POST /auth/session: one-time jti + DB + Redis cache."""
    try:
        claims = decode_short_lived_jwt(token, settings)
    except ValueError as exc:
        raise AgentFactoryException(
            "TOKEN_EXPIRED",
            "Short-lived token invalid or expired",
            status_code=401,
        ) from exc

    jti = str(claims.get("jti") or "")
    if not jti:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Token missing jti",
            status_code=400,
        )

    used = await redis.get(_redis_jti_key(jti))
    if used:
        raise AgentFactoryException(
            "TOKEN_REUSED",
            "Short-lived token already consumed",
            status_code=401,
        )

    sub = str(claims.get("sub") or "")
    department = claims.get("department")
    if department is not None:
        department = str(department)
    perms = claims.get("permissions")
    if isinstance(perms, list):
        perm_list = [str(p) for p in perms]
    else:
        perm_list = []

    uid_hash = hash_user_id(sub, settings.USER_ID_HASH_SALT)
    rev_snap = await fetch_revoke_gen_snapshot(redis, uid_hash)
    sid = f"sess_{secrets.token_hex(24)}"
    now = _utc_naive()
    expires = now + timedelta(seconds=settings.SESSION_COOKIE_MAX_AGE)
    allowed_stored = _allowed_tuple_from_claims(claims)
    domain_stored = normalized_portal_data_domains(claims)

    row = ChatSession(
        session_id=sid,
        run_id=None,
        user_id_hash=uid_hash,
        agent_id=None,
        department=department,
        status="created",
        turn_count=0,
        total_tokens=0,
        created_at=now,
        last_activity=now,
        expires_at=expires,
        allowed_agents=allowed_stored,
        data_domains=domain_stored,
        permissions=perm_list,
        revoke_gen_seen=rev_snap,
    )
    db.add(row)
    await db.flush()

    await redis.set(
        _redis_jti_key(jti),
        "1",
        ex=max(settings.JWT_EXPIRE_SECONDS, 300),
    )

    cache: dict[str, Any] = {
        "user_id_hash": uid_hash,
        "department": department,
        "permissions": perm_list,
        "expires_at": expires.isoformat(),
        "revoke_gen": rev_snap,
    }
    if allowed_stored is not None:
        cache["allowed_agents"] = allowed_stored
    if domain_stored is not None:
        cache["data_domains"] = domain_stored
    await redis.set(
        _redis_sess_key(sid),
        json.dumps(cache),
        ex=settings.SESSION_COOKIE_MAX_AGE + 120,
    )
    return row


async def bootstrap_dev_widget_session(
    *,
    db: AsyncSession,
    redis: Redis,
    settings: Settings,
    agent_id: str,
) -> ChatSession:
    """Create session cookie without portal exchange (local dev only)."""
    if settings.APP_ENV != "development" or not settings.DEV_WIDGET_AUTH_BYPASS:
        raise AgentFactoryException(
            "FORBIDDEN",
            "Dev widget bypass is disabled",
            status_code=403,
        )

    agent_row = await _load_agent(db, agent_id)
    if agent_row is None:
        raise AgentFactoryException(
            "AGENT_NOT_FOUND",
            f"Agent not found: {agent_id}",
            status_code=404,
        )
    if agent_row.lifecycle_state != "active":
        raise AgentFactoryException(
            "AGENT_INACTIVE",
            "Agent is not active",
            status_code=403,
        )

    sub = "local-dev-user"
    department = "dev"
    # 本地联调：授予注册中心 / 运营台所需权限（勿用于生产）
    perm_list = ["agent.read", "agent.write", "agent.admin"]
    uid_hash = hash_user_id(sub, settings.USER_ID_HASH_SALT)
    sid = f"sess_{secrets.token_hex(24)}"
    now = _utc_naive()
    expires = now + timedelta(seconds=settings.SESSION_COOKIE_MAX_AGE)

    row = ChatSession(
        session_id=sid,
        run_id=None,
        user_id_hash=uid_hash,
        agent_id=None,
        department=department,
        status="created",
        turn_count=0,
        total_tokens=0,
        created_at=now,
        last_activity=now,
        expires_at=expires,
        allowed_agents=None,
        permissions=perm_list,
        revoke_gen_seen=0,
    )
    db.add(row)
    await db.flush()

    cache = {
        "user_id_hash": uid_hash,
        "department": department,
        "permissions": perm_list,
        "expires_at": expires.isoformat(),
        "revoke_gen": 0,
    }
    await redis.set(
        _redis_sess_key(sid),
        json.dumps(cache),
        ex=settings.SESSION_COOKIE_MAX_AGE + 120,
    )
    return row


async def resolve_user_context(
    *,
    db: AsyncSession,
    redis: Redis,
    settings: Settings,
    session_id: str,
) -> UserContext:
    """Load user from Redis cache or DB session row."""
    raw = await redis.get(_redis_sess_key(session_id))
    if raw:
        data = json.loads(raw)
        exp = data.get("expires_at")
        if exp:
            exp_s = str(exp).replace("Z", "+00:00")
            exp_dt = datetime.fromisoformat(exp_s)
            if exp_dt.tzinfo is not None:
                exp_dt = exp_dt.astimezone(UTC).replace(tzinfo=None)
            if exp_dt < _utc_naive():
                raise AgentFactoryException(
                    "SESSION_EXPIRED",
                    "Session expired",
                    status_code=401,
                )
        uid_h = str(data["user_id_hash"])
        cur_rev = await fetch_revoke_gen_snapshot(redis, uid_h)
        if cur_rev > int(data.get("revoke_gen", 0)):
            await redis.delete(_redis_sess_key(session_id))
            raise AgentFactoryException(
                "SESSION_REVOKED",
                "会话已被门户或运维撤销，请重新登录",
                status_code=401,
            )
        perms = data.get("permissions") or []
        aa = _user_allowed_tuple(data.get("allowed_agents"))
        dd = _user_data_domains_tuple(data.get("data_domains"))
        return UserContext(
            session_id=session_id,
            user_id_hash=uid_h,
            department=data.get("department"),
            permissions=tuple(str(p) for p in perms),
            allowed_agents=aa,
            data_domains=dd,
        )

    q = await db.execute(
        select(ChatSession).where(ChatSession.session_id == session_id)
    )
    row = q.scalar_one_or_none()
    if row is None or row.expires_at is None:
        raise AgentFactoryException(
            "SESSION_REQUIRED",
            "Valid session required",
            status_code=401,
        )
    if row.expires_at < _utc_naive():
        raise AgentFactoryException(
            "SESSION_EXPIRED",
            "Session expired",
            status_code=401,
        )
    rev_row = int(row.revoke_gen_seen or 0)
    cur_rev = await fetch_revoke_gen_snapshot(redis, row.user_id_hash)
    if cur_rev > rev_row:
        raise AgentFactoryException(
            "SESSION_REVOKED",
            "会话已被门户或运维撤销，请重新登录",
            status_code=401,
        )
    perms_row = row.permissions if isinstance(row.permissions, list) else []
    aa_db = _user_allowed_tuple(row.allowed_agents)
    dd_db = _user_data_domains_tuple(row.data_domains)
    cache: dict[str, Any] = {
        "user_id_hash": row.user_id_hash,
        "department": row.department,
        "permissions": [str(p) for p in perms_row],
        "expires_at": row.expires_at.isoformat(),
        "revoke_gen": rev_row,
    }
    if aa_db is not None:
        cache["allowed_agents"] = list(aa_db)
    if dd_db is not None:
        cache["data_domains"] = list(dd_db)
    await redis.set(
        _redis_sess_key(session_id),
        json.dumps(cache),
        ex=settings.SESSION_COOKIE_MAX_AGE + 120,
    )
    return UserContext(
        session_id=session_id,
        user_id_hash=row.user_id_hash,
        department=row.department,
        permissions=tuple(str(p) for p in perms_row),
        allowed_agents=aa_db,
        data_domains=dd_db,
    )


async def heartbeat_session(
    *,
    db: AsyncSession,
    redis: Redis,
    settings: Settings,
    session_id: str,
) -> None:
    """Extend DB + Redis + caller sets Set-Cookie."""
    q = await db.execute(
        select(ChatSession).where(ChatSession.session_id == session_id)
    )
    row = q.scalar_one_or_none()
    if row is None:
        raise AgentFactoryException(
            "SESSION_EXPIRED",
            "Session not found",
            status_code=401,
        )
    now = _utc_naive()
    new_exp = now + timedelta(seconds=settings.SESSION_COOKIE_MAX_AGE)
    row.expires_at = new_exp
    row.last_activity = now

    raw = await redis.get(_redis_sess_key(session_id))
    if raw:
        data = json.loads(raw)
        data["expires_at"] = new_exp.isoformat()
        await redis.set(
            _redis_sess_key(session_id),
            json.dumps(data),
            ex=settings.SESSION_COOKIE_MAX_AGE + 120,
        )


async def sync_session_permissions_from_portal(
    *,
    db: AsyncSession,
    redis: Redis,
    settings: Settings,
    session_id: str,
    portal_authorization: str,
) -> dict[str, Any]:
    """门户重新签发 JWT 后刷新本会话的 permissions（docs/51 阶段 D）。"""
    if not portal_authorization.lower().startswith("bearer "):
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Authorization Bearer portal JWT required",
            status_code=400,
        )
    raw_jwt = portal_authorization.split(" ", 1)[1].strip()
    try:
        claims = verify_portal_jwt(raw_jwt, settings)
    except ValueError as exc:
        msg = str(exc)
        status = 400 if "not configured" in msg else 401
        raise AgentFactoryException(
            "INVALID_PARAMS",
            msg,
            status_code=status,
        ) from exc

    sub = str(claims.get("sub") or "")
    if not sub:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Portal JWT missing sub",
            status_code=400,
        )
    uid_expected = hash_user_id(sub, settings.USER_ID_HASH_SALT)
    q = await db.execute(
        select(ChatSession).where(ChatSession.session_id == session_id)
    )
    row = q.scalar_one_or_none()
    if row is None:
        raise AgentFactoryException(
            "SESSION_EXPIRED",
            "Session not found",
            status_code=401,
        )
    if row.user_id_hash != uid_expected:
        raise AgentFactoryException(
            "FORBIDDEN",
            "Portal sub does not match session user",
            status_code=403,
        )

    department = claims.get("department")
    if department is not None:
        department = str(department)
    perms = claims.get("permissions")
    if isinstance(perms, list):
        perm_list = [str(p) for p in perms]
    else:
        perm_list = []
    portal_allowed = normalized_portal_allowed_agents(claims)
    portal_domains = normalized_portal_data_domains(claims)

    row.permissions = perm_list
    row.department = department
    row.allowed_agents = portal_allowed
    row.data_domains = portal_domains
    await db.flush()

    sess_key = _redis_sess_key(session_id)
    r_raw = await redis.get(sess_key)
    if r_raw:
        data = json.loads(r_raw)
        if str(data.get("user_id_hash")) != row.user_id_hash:
            raise AgentFactoryException(
                "FORBIDDEN",
                "Redis session mismatch",
                status_code=403,
            )
        data["permissions"] = perm_list
        data["department"] = department
        if portal_allowed is not None:
            data["allowed_agents"] = portal_allowed
        else:
            data.pop("allowed_agents", None)
        if portal_domains is not None:
            data["data_domains"] = portal_domains
        else:
            data.pop("data_domains", None)
        await redis.set(
            sess_key,
            json.dumps(data),
            ex=settings.SESSION_COOKIE_MAX_AGE + 120,
        )
    return {"status": "ok", "permissions": perm_list}
