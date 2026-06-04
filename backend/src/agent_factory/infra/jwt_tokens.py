"""Portal JWT verification and short-lived widget JWT (docs/06-api-gateway)."""

from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
from jwt import PyJWTError

from agent_factory.config import Settings


def _short_secret(settings: Settings) -> str:
    if not settings.JWT_SECRET:
        raise ValueError("JWT_SECRET is required to sign short-lived tokens")
    return settings.JWT_SECRET


def verify_portal_jwt(token: str, settings: Settings) -> dict[str, Any]:
    """Validate portal-issued JWT (HS256 or RS256)."""
    try:
        if settings.PORTAL_JWT_PUBLIC_KEY.strip():
            key = settings.PORTAL_JWT_PUBLIC_KEY.strip()
            return jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
        if settings.PORTAL_JWT_SECRET:
            return jwt.decode(
                token,
                settings.PORTAL_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
    except PyJWTError as exc:
        raise ValueError("Portal JWT invalid or expired") from exc
    raise ValueError(
        "Portal JWT verification is not configured: set "
        "PORTAL_JWT_SECRET (HS256) or PORTAL_JWT_PUBLIC_KEY (RS256 PEM)"
    )


def issue_short_lived_jwt(
    *,
    settings: Settings,
    sub: str,
    department: str | None,
    agent_id: str,
    permissions: list[str],
    allowed_agents: list[str] | None = None,
    data_domains: list[str] | None = None,
) -> tuple[str, int, str]:
    """Return (token, expires_at_unix, jti).

    When ``allowed_agents`` is set (including empty list), it is embedded so
    the widget session can filter ``GET /agents`` (prd §4.5.5). When omitted,
    portal did not supply a restriction list.

    When ``data_domains`` is set (including empty list), it is embedded for
    RunSpec retrieval intersection (docs/07). When omitted, portal did not
    supply the claim.
    """
    now = int(time.time())
    exp = now + settings.JWT_EXPIRE_SECONDS
    jti = f"jti_{uuid.uuid4().hex}"
    payload: dict[str, Any] = {
        "sub": sub,
        "department": department,
        "agent_id": agent_id,
        "scope": "agent.run",
        "permissions": permissions,
        "iat": now,
        "exp": exp,
        "jti": jti,
    }
    if allowed_agents is not None:
        payload["allowed_agents"] = list(allowed_agents)
    if data_domains is not None:
        payload["data_domains"] = list(data_domains)
    token = jwt.encode(
        payload,
        _short_secret(settings),
        algorithm=settings.JWT_ALGORITHM,
    )
    if isinstance(token, bytes):
        token = token.decode("ascii")
    return token, exp, jti


def decode_short_lived_jwt(token: str, settings: Settings) -> dict[str, Any]:
    """Validate short-lived JWT from widget URL."""
    try:
        return jwt.decode(
            token,
            _short_secret(settings),
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "jti", "sub"]},
        )
    except (PyJWTError, ValueError) as exc:
        raise ValueError("invalid_or_expired_short_token") from exc


def _admin_signing_secret(settings: Settings) -> str:
    s = (settings.ADMIN_JWT_SECRET or settings.JWT_SECRET or "").strip()
    if not s:
        raise ValueError("ADMIN_JWT_SECRET or JWT_SECRET required for admin JWT")
    return s


def issue_admin_panel_jwt(
    *,
    settings: Settings,
    subject: str,
    permissions: list[str],
) -> tuple[str, int]:
    """Return (token, expires_at_unix) for management UI (docs/19)."""
    now = int(time.time())
    ttl = int(settings.ADMIN_PANEL_JWT_TTL_SECONDS)
    exp = now + ttl
    payload: dict[str, Any] = {
        "sub": subject,
        "af_admin": True,
        "permissions": list(permissions),
        "iat": now,
        "exp": exp,
        "scope": "admin.panel",
    }
    token = jwt.encode(
        payload,
        _admin_signing_secret(settings),
        algorithm="HS256",
    )
    if isinstance(token, bytes):
        token = token.decode("ascii")
    return token, exp


def verify_admin_panel_jwt(token: str, settings: Settings) -> dict[str, Any]:
    """Validate admin panel JWT from Authorization header."""
    try:
        return jwt.decode(
            token,
            _admin_signing_secret(settings),
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub"]},
        )
    except PyJWTError as exc:
        raise ValueError("invalid_admin_jwt") from exc
