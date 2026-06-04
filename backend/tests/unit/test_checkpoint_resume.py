"""Tests for checkpoint resume with timestamp tie-breaker."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_factory.services.runner_service import RunnerService


@pytest.mark.asyncio
async def test_load_history_takes_latest_timestamp_for_same_turn():
    """Insert multiple checkpoints with same turn_number; _load_history picks latest."""
    svc = RunnerService(MagicMock(), MagicMock())

    # Build fake checkpoints with same turn_number but different timestamps
    cp_old = MagicMock()
    cp_old.messages = [{"role": "user", "content": "old"}]
    cp_old.timestamp = datetime(2024, 1, 1, 10, 0, 0)
    cp_old.last_summarized_message_index = None

    cp_new = MagicMock()
    cp_new.messages = [{"role": "user", "content": "new"}]
    cp_new.timestamp = datetime(2024, 1, 1, 10, 0, 1)
    cp_new.last_summarized_message_index = None

    # Mock db.execute to return both in a result that simulates DB ordering
    mock_result = MagicMock()
    # scalar_one_or_none should return the first (newest) because we order by timestamp desc
    mock_result.scalar_one_or_none.return_value = cp_new

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    session = MagicMock()
    session.run_id = "run_1"

    msgs, last_idx = await svc._load_history(db, session)
    assert len(msgs) == 1
    assert msgs[0]["content"] == "new"
    assert last_idx is None

    # Verify the query was constructed with correct ordering
    call_args = db.execute.await_args
    built_query = call_args[0][0]
    # Extract order_by clauses from the SQLAlchemy query object
    order_by = getattr(built_query, "_order_by_clauses", [])
    # Should have at least 2 order_by clauses (turn_number.desc, timestamp.desc)
    assert len(order_by) >= 2
