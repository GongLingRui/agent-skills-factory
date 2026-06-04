"""Tests for token quota service."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services import quota_service as qsvc


def _make_result(value: Any | list[Any] | None) -> MagicMock:
    r = MagicMock()
    if isinstance(value, list):
        r.scalars.return_value.all.return_value = value
        r.scalar_one_or_none.return_value = value[0] if value else None
    else:
        r.scalars.return_value.all.return_value = [value] if value is not None else []
        r.scalar_one_or_none.return_value = value
    return r


class _FakeQuota:
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.mark.asyncio
async def test_list_quotas_empty():
    db = AsyncMock()
    db.execute.return_value = _make_result(None)
    out = await qsvc.list_quotas(db, scope=None, scope_id=None, period=None)
    assert out == []


@pytest.mark.asyncio
async def test_list_quotas_with_row():
    db = AsyncMock()
    fake = _FakeQuota(
        scope="department", scope_id="dept-a",
        budget_tokens=1000000, used_tokens=250000,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    db.execute.return_value = _make_result(fake)
    out = await qsvc.list_quotas(db, scope="department", scope_id="dept-a", period="2026-05")
    assert len(out) == 1
    assert out[0]["budget_tokens"] == 1000000
    assert out[0]["used_tokens"] == 250000
    assert out[0]["usage_rate"] == 0.25


@pytest.mark.asyncio
async def test_list_quotas_invalid_scope():
    db = AsyncMock()
    with pytest.raises(AgentFactoryException) as exc:
        await qsvc.list_quotas(db, scope="invalid", scope_id=None, period=None)
    assert exc.value.code == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_check_quota_allows_estimate_no_row():
    db = AsyncMock()
    db.execute.return_value = _make_result(None)
    await qsvc.check_quota_allows_estimate(db, scope="user", scope_id="u1", estimated_tokens=1000)


@pytest.mark.asyncio
async def test_check_quota_allows_estimate_exceeded():
    db = AsyncMock()
    fake = _FakeQuota(
        scope="user", scope_id="u1", budget_tokens=100, used_tokens=50,
        period_start=date.today().replace(day=1),
        period_end=date.today().replace(day=28),
    )
    db.execute.return_value = _make_result(fake)
    with pytest.raises(AgentFactoryException) as exc:
        await qsvc.check_quota_allows_estimate(db, scope="user", scope_id="u1", estimated_tokens=100)
    assert exc.value.code == "TOKEN_QUOTA_EXCEEDED"


@pytest.mark.asyncio
async def test_increment_used_tokens_noop():
    db = AsyncMock()
    await qsvc.increment_used_tokens(db, scope="user", scope_id="u1", tokens=0)
    db.execute.assert_not_called()
