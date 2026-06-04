"""Skill Registry eval gate (docs/04)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.skill_eval_gate import (
    effective_eval_gate_rpm,
    enforce_eval_gate_rpm_slot,
    extract_eval_cases,
    run_skill_registry_eval_gate,
    validate_eval_cases_schema,
)


def _valid_case() -> dict:
    return {
        "id": "c1",
        "name": "case one",
        "input": {"message": "ping"},
        "min_score": 0.0,
    }


def test_extract_empty() -> None:
    assert extract_eval_cases(None) == []
    assert extract_eval_cases({}) == []


def test_extract_eval_cases_key() -> None:
    c = _valid_case()
    assert extract_eval_cases({"eval_cases": [c]}) == [c]


def test_extract_invalid_type() -> None:
    with pytest.raises(AgentFactoryException) as exc:
        extract_eval_cases({"eval_cases": "not-list"})
    assert exc.value.code == "INVALID_EVAL_CASES"


def test_validate_schema_ok() -> None:
    validate_eval_cases_schema([_valid_case()])


def test_validate_schema_bad() -> None:
    with pytest.raises(AgentFactoryException) as exc:
        validate_eval_cases_schema(
            [{"id": "", "name": "x", "input": {"message": "m"}, "min_score": 0.5}]
        )
    assert exc.value.code == "EVAL_CASES_INVALID"


def test_effective_eval_gate_rpm_override() -> None:
    from agent_factory.config.settings import Settings

    s = Settings.model_construct(SKILL_EVAL_GATE_RPM=7)
    gw = MagicMock()
    gw.rpm_for.return_value = 99
    assert effective_eval_gate_rpm(s, gw, "any") == 7


def test_effective_eval_gate_rpm_from_yaml() -> None:
    from agent_factory.config.settings import Settings

    s = Settings.model_construct(SKILL_EVAL_GATE_RPM=0)
    gw = MagicMock()
    gw.rpm_for.return_value = 44
    assert effective_eval_gate_rpm(s, gw, "m") == 44


@pytest.mark.asyncio
async def test_enforce_eval_gate_rpm_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRedis:
        async def incr(self, key: str) -> int:
            return 11

        async def expire(self, key: str, ttl: int) -> bool:
            return True

    monkeypatch.setattr(
        "agent_factory.services.skill_eval_gate.get_redis",
        lambda: FakeRedis(),
    )
    with pytest.raises(AgentFactoryException) as exc:
        await enforce_eval_gate_rpm_slot(logical_model="MiniMax-M2.7", rpm_limit=10)
    assert exc.value.code == "EVAL_GATE_RATE_LIMITED"


@pytest.mark.asyncio
async def test_run_gate_live_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILL_EVAL_GATE_LIVE", "false")
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    try:
        await run_skill_registry_eval_gate(
            package_metadata={"eval_cases": [_valid_case()]},
            settings=get_settings(),
        )
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_eval_cases_required_empty_raises() -> None:
    from agent_factory.config.settings import Settings

    with pytest.raises(AgentFactoryException) as exc:
        await run_skill_registry_eval_gate(
            package_metadata=None,
            settings=Settings.model_construct(SKILL_EVAL_CASES_REQUIRED=True),
        )
    assert exc.value.code == "EVAL_CASES_REQUIRED"


@pytest.mark.asyncio
async def test_eval_cases_empty_ok_when_not_required() -> None:
    from agent_factory.config.settings import Settings

    await run_skill_registry_eval_gate(
        package_metadata={},
        settings=Settings.model_construct(SKILL_EVAL_CASES_REQUIRED=False),
    )
