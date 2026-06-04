"""Unit tests for JWT helpers (no DB)."""

import time

import jwt
import pytest

from agent_factory.config import Settings
from agent_factory.infra.jwt_tokens import (
    decode_short_lived_jwt,
    issue_short_lived_jwt,
    verify_portal_jwt,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        JWT_SECRET="x" * 32 + "-short-jwt-secret-test",
        PORTAL_JWT_SECRET="x" * 32 + "-portal-secret-test",
        JWT_EXPIRE_SECONDS=60,
        PORTAL_JWT_PUBLIC_KEY="",
    )


def test_portal_roundtrip(settings: Settings) -> None:
    token = jwt.encode(
        {"sub": "user-1", "department": "legal"},
        settings.PORTAL_JWT_SECRET,
        algorithm="HS256",
    )
    claims = verify_portal_jwt(
        token if isinstance(token, str) else token.decode("ascii"),
        settings,
    )
    assert claims["sub"] == "user-1"
    assert claims["department"] == "legal"


def test_short_lived_roundtrip(settings: Settings) -> None:
    st, exp, jti = issue_short_lived_jwt(
        settings=settings,
        sub="user-1",
        department="legal",
        agent_id="demo-agent",
        permissions=["kb.search"],
    )
    assert exp > int(time.time())
    assert jti.startswith("jti_")
    out = decode_short_lived_jwt(st, settings)
    assert out["sub"] == "user-1"
    assert out["agent_id"] == "demo-agent"
    assert out["permissions"] == ["kb.search"]


def test_short_lived_allowed_agents_in_payload(settings: Settings) -> None:
    st, _exp, _jti = issue_short_lived_jwt(
        settings=settings,
        sub="user-1",
        department=None,
        agent_id="a1",
        permissions=[],
        allowed_agents=["a1", "a2"],
    )
    out = decode_short_lived_jwt(st, settings)
    assert out.get("allowed_agents") == ["a1", "a2"]


def test_short_lived_empty_allowed_agents(settings: Settings) -> None:
    st, _exp, _jti = issue_short_lived_jwt(
        settings=settings,
        sub="user-1",
        department=None,
        agent_id="a1",
        permissions=[],
        allowed_agents=[],
    )
    out = decode_short_lived_jwt(st, settings)
    assert out.get("allowed_agents") == []


def test_short_lived_data_domains_roundtrip(settings: Settings) -> None:
    st, _exp, _jti = issue_short_lived_jwt(
        settings=settings,
        sub="user-1",
        department=None,
        agent_id="a1",
        permissions=[],
        data_domains=["corp-a", "corp-b"],
    )
    out = decode_short_lived_jwt(st, settings)
    assert out.get("data_domains") == ["corp-a", "corp-b"]


def test_short_lived_empty_data_domains_in_payload(settings: Settings) -> None:
    st, _exp, _jti = issue_short_lived_jwt(
        settings=settings,
        sub="user-1",
        department=None,
        agent_id="a1",
        permissions=[],
        data_domains=[],
    )
    out = decode_short_lived_jwt(st, settings)
    assert out.get("data_domains") == []
