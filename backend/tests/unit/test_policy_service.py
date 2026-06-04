"""Tests for policy service CRUD with versioning."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services import policy_service as psvc


def _make_result(value: Any | list[Any] | None) -> MagicMock:
    r = MagicMock()
    if isinstance(value, list):
        r.scalars.return_value.all.return_value = value
        r.scalar_one_or_none.return_value = value[0] if value else None
        r.scalar_one.return_value = value[0] if value else None
    else:
        r.scalars.return_value.all.return_value = [value] if value is not None else []
        r.scalar_one_or_none.return_value = value
        r.scalar_one.return_value = value
    return r


class _FakePolicy:
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.mark.asyncio
async def test_list_platform_policies():
    db = AsyncMock()
    now = datetime.now(UTC).replace(tzinfo=None)
    fake = _FakePolicy(
        lineage_id="safe", version=1, prompt="be safe", enabled=True,
        created_at=now, updated_at=now,
    )
    db.execute.return_value = _make_result([fake])
    out = await psvc.list_platform_policies(db)
    assert len(out) == 1
    assert out[0]["id"] == "safe"
    assert out[0]["enabled"] is True


@pytest.mark.asyncio
async def test_create_platform_policy_version():
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [
        _make_result(0),   # max version
        MagicMock(),        # update
    ]
    out = await psvc.create_platform_policy_version(db, lineage_id="safe", prompt="be safe", enabled=True)
    assert out["id"] == "safe"
    assert out["version"] == 1


@pytest.mark.asyncio
async def test_create_platform_policy_version_increments():
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [
        _make_result(5),    # max version
        MagicMock(),         # update
    ]
    out = await psvc.create_platform_policy_version(db, lineage_id="safe", prompt="be safe", enabled=False)
    assert out["version"] == 6


@pytest.mark.asyncio
async def test_list_org_policies():
    db = AsyncMock()
    now = datetime.now(UTC).replace(tzinfo=None)
    fake = _FakePolicy(
        lineage_id="dept-safe", version=1, department="dept-a",
        prompt="be safe", enabled=True, created_at=now, updated_at=now,
    )
    db.execute.return_value = _make_result([fake])
    out = await psvc.list_org_policies(db, "dept-a")
    assert len(out) == 1
    assert out[0]["id"] == "dept-safe"


@pytest.mark.asyncio
async def test_assert_org_lineage_department_ok():
    db = AsyncMock()
    db.execute.return_value = _make_result("dept-a")
    await psvc.assert_org_lineage_department(db, lineage_id="x", department="dept-a")


@pytest.mark.asyncio
async def test_assert_org_lineage_department_mismatch():
    db = AsyncMock()
    db.execute.return_value = _make_result("dept-b")
    with pytest.raises(AgentFactoryException) as exc:
        await psvc.assert_org_lineage_department(db, lineage_id="x", department="dept-a")
    assert exc.value.code == "INVALID_PARAMS"
