"""Tests for transcript_service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_factory.services.transcript_service import record_event


@pytest.mark.asyncio
async def test_record_event():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    await record_event(
        db,
        run_id="run_1",
        session_id="sess_1",
        turn_number=1,
        event_type="model_call_start",
        payload={"message_id": "m1"},
    )
    db.add.assert_called_once()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_event_swallows_exception():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=RuntimeError("DB down"))
    # should not raise
    await record_event(
        db,
        run_id="run_1",
        session_id="sess_1",
        turn_number=1,
        event_type="model_call_start",
        payload={},
    )
