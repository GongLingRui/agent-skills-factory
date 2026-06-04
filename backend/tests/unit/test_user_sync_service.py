"""Tests for user/department sync service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services import user_sync_service as usvc


def _make_result(value: Any | list[Any] | None) -> MagicMock:
    r = MagicMock()
    if isinstance(value, list):
        r.scalars.return_value.all.return_value = value
        r.scalar_one_or_none.return_value = value[0] if value else None
    else:
        r.scalars.return_value.all.return_value = [value] if value is not None else []
        r.scalar_one_or_none.return_value = value
    return r


class _FakeUser:
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeOverlay:
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeDept:
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.mark.asyncio
async def test_list_users_page():
    db = AsyncMock()
    user = _FakeUser(
        user_id="u1", display_name="Alice", department="dept-a",
        portal_roles=["agent.user"], synced_at=None,
    )
    overlay = _FakeOverlay(user_id="u1", roles=["agent.admin"])
    db.execute.side_effect = [
        _make_result([user]),
        _make_result([overlay]),
    ]
    items, total = await usvc.list_users_page(db, department="dept-a", page=1, page_size=20)
    assert total == 1
    assert items[0]["user_id"] == "u1"
    assert items[0]["roles"] == ["agent.admin"]


@pytest.mark.asyncio
async def test_upsert_user_roles_overlay_self_forbidden():
    db = AsyncMock()
    with pytest.raises(AgentFactoryException) as exc:
        await usvc.upsert_user_roles_overlay(
            db, user_id="u1", roles=["admin"], reason=None,
            operator_id="op", actor_user_id="u1",
        )
    assert exc.value.code == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_replace_directory_snapshot():
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [
        _make_result(None),  # dept query
        _make_result(None),  # user query
    ]
    stats = await usvc.replace_directory_snapshot(
        db,
        users=[{"user_id": "u1", "name": "Alice", "department": "dept-a", "roles": []}],
        departments=[{"code": "dept-a", "name": "Dept A"}],
    )
    assert stats["users"] == 1
    assert stats["departments"] == 1


@pytest.mark.asyncio
async def test_list_departments_flat():
    db = AsyncMock()
    dept = _FakeDept(code="dept-a", name="Dept A", parent_code=None, synced_at=None)
    db.execute.return_value = _make_result([dept])
    out = await usvc.list_departments_flat(db)
    assert len(out) == 1
    assert out[0]["code"] == "dept-a"
