"""Redis circuit breaker helpers for HTTP tools."""

import pytest

from agent_factory.config.settings import Settings
from agent_factory.infra.tool_circuit_breaker import (
    HttpToolCircuitConfig,
    assert_http_tool_circuit_closed,
    build_http_tool_circuit_config,
    clear_http_tool_failures,
    failure_counts_toward_circuit,
    http_tool_circuit_scope,
    record_http_tool_failure,
)
from agent_factory.middleware.error_handler import AgentFactoryException


class _MemRedis:
    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.ints: dict[str, int] = {}

    async def get(self, key: str):
        return self.strings.get(key)

    async def set(self, key: str, val: str, ex: int | None = None):
        self.strings[key] = val

    async def incr(self, key: str) -> int:
        self.ints[key] = self.ints.get(key, 0) + 1
        return self.ints[key]

    async def expire(self, key: str, sec: int) -> bool:
        return True

    async def delete(self, key: str) -> None:
        self.strings.pop(key, None)
        self.ints.pop(key, None)


def test_scope_with_department():
    assert http_tool_circuit_scope("t1", None, per_department=True) == "t1"
    assert (
        http_tool_circuit_scope("t1", "hq", per_department=True) == "t1:d:hq"
    )


@pytest.mark.asyncio
async def test_open_blocks_calls():
    r = _MemRedis()
    await r.set("cb:httptool:t1:open", "1", ex=30)
    cfg = HttpToolCircuitConfig(True, 3, 60, 30)
    with pytest.raises(AgentFactoryException) as ei:
        await assert_http_tool_circuit_closed(r, "t1", cfg)
    assert ei.value.code == "TOOL_CIRCUIT_OPEN"


@pytest.mark.asyncio
async def test_failures_open_circuit():
    r = _MemRedis()
    cfg = HttpToolCircuitConfig(True, 3, 60, 30)
    await record_http_tool_failure(r, "x", cfg)
    await record_http_tool_failure(r, "x", cfg)
    await record_http_tool_failure(r, "x", cfg)
    assert await r.get("cb:httptool:x:open") == "1"


@pytest.mark.asyncio
async def test_success_clears_fail_counter():
    r = _MemRedis()
    await r.incr("cb:httptool:z:fail")
    await clear_http_tool_failures(r, "z")
    assert r.ints.get("cb:httptool:z:fail") is None


def test_build_config_merges_row():
    s = Settings(
        TOOL_HTTP_CIRCUIT_ENABLED=True,
        TOOL_HTTP_CIRCUIT_FAILURE_THRESHOLD=5,
        TOOL_HTTP_CIRCUIT_WINDOW_SECONDS=60,
        TOOL_HTTP_CIRCUIT_OPEN_SECONDS=30,
    )
    cfg = build_http_tool_circuit_config(
        s,
        {"circuit_breaker": {"failure_threshold": 2}},
    )
    assert cfg.failure_threshold == 2
    assert cfg.enabled is True


def test_failure_codes():
    assert failure_counts_toward_circuit(
        AgentFactoryException("TOOL_HTTP_TRANSPORT", "x", 502)
    )
    assert not failure_counts_toward_circuit(
        AgentFactoryException("TOOL_HTTP_CLIENT_ERROR", "x", 400)
    )
