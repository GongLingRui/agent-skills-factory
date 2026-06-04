"""MAU retention gate (plan §13.1, docs/21, workers/retention_mau)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_factory.config.settings import Settings
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.workers.retention_mau import (
    _mau_threshold_for_agent,
    run_mau_retention_gate,
)


def test_mau_threshold_from_enterprise_config():
    agent = AgentApp()
    agent.enterprise_config = {"mau_threshold": 12}
    assert _mau_threshold_for_agent(agent, 5) == 12


def test_mau_threshold_invalid_falls_back_to_default():
    agent = AgentApp()
    agent.enterprise_config = {"mau_threshold": "x"}
    assert _mau_threshold_for_agent(agent, 7) == 7


def test_mau_threshold_none_uses_default():
    agent = AgentApp()
    agent.enterprise_config = {}
    assert _mau_threshold_for_agent(agent, 5) == 5


@pytest.mark.asyncio
async def test_run_mau_retention_gate_noop_when_disabled():
    db = AsyncMock()
    s = Settings.model_construct(MAU_RETENTION_GATE_ENABLED=False)
    await run_mau_retention_gate(db, s)
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_run_mau_retention_marks_low_mau_cold():
    """Active agent with MAU below default threshold becomes cold."""
    agent = AgentApp()
    agent.id = "low-traffic"
    agent.lifecycle_state = "active"
    agent.enterprise_config = None
    agent.degradation_exempt = False
    agent.cold_since = None

    mau_iter = iter([])
    mau_result = MagicMock()
    mau_result.__iter__ = lambda self: mau_iter

    agents_result = MagicMock()
    agents_result.scalars.return_value = [agent]

    arch_result = MagicMock()
    arch_result.rowcount = 0

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[mau_result, agents_result, arch_result])

    s = Settings.model_construct(
        MAU_RETENTION_GATE_ENABLED=True,
        MAU_RETENTION_WINDOW_DAYS=30,
        MAU_RETENTION_DEFAULT_THRESHOLD=5,
        MAU_COLD_ARCHIVE_AFTER_DAYS=90,
    )
    await run_mau_retention_gate(db, s)

    assert agent.lifecycle_state == "cold"
    assert agent.cold_since is not None
    assert db.execute.await_count == 3


@pytest.mark.asyncio
async def test_run_mau_retention_skips_exempt_agent():
    agent = AgentApp()
    agent.id = "exempt"
    agent.lifecycle_state = "active"
    agent.degradation_exempt = True

    mau_iter = iter([])
    mau_result = MagicMock()
    mau_result.__iter__ = lambda self: mau_iter

    agents_result = MagicMock()
    agents_result.scalars.return_value = [agent]

    arch_result = MagicMock()
    arch_result.rowcount = 0

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[mau_result, agents_result, arch_result])

    s = Settings.model_construct(
        MAU_RETENTION_GATE_ENABLED=True,
        MAU_RETENTION_WINDOW_DAYS=30,
        MAU_RETENTION_DEFAULT_THRESHOLD=5,
        MAU_COLD_ARCHIVE_AFTER_DAYS=90,
    )
    await run_mau_retention_gate(db, s)

    assert agent.lifecycle_state == "active"


@pytest.mark.asyncio
async def test_run_mau_archives_long_idle_cold():
    """Cold agents with cold_since older than cutoff are archived."""
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=100)
    cold_agent = AgentApp()
    cold_agent.id = "stale-cold"
    cold_agent.lifecycle_state = "cold"
    cold_agent.cold_since = old
    cold_agent.degradation_exempt = False

    mau_iter = iter([])
    mau_result = MagicMock()
    mau_result.__iter__ = lambda self: mau_iter

    active_agents_result = MagicMock()
    active_agents_result.scalars.return_value = []

    arch_result = MagicMock()
    arch_result.rowcount = 1

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[mau_result, active_agents_result, arch_result]
    )

    s = Settings.model_construct(
        MAU_RETENTION_GATE_ENABLED=True,
        MAU_RETENTION_WINDOW_DAYS=30,
        MAU_RETENTION_DEFAULT_THRESHOLD=5,
        MAU_COLD_ARCHIVE_AFTER_DAYS=90,
    )
    await run_mau_retention_gate(db, s)

    assert db.execute.await_count == 3
