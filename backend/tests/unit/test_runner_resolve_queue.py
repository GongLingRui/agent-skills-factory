"""Runner model queue context (degradation_exempt → privileged)."""

from types import SimpleNamespace

import pytest

from agent_factory.services.runner_service import _resolve_model_queue_context


class _Result:
    def __init__(self, cell: object) -> None:
        self._cell = cell

    def scalar_one_or_none(self) -> object:
        return self._cell


class _Session:
    def __init__(self, cell: object) -> None:
        self._cell = cell

    async def execute(self, *_a, **_k) -> _Result:
        return _Result(self._cell)


@pytest.mark.asyncio
async def test_exempt_agent_gets_privileged_priority_10():
    db = _Session(True)  # type: ignore[arg-type]
    rs = SimpleNamespace(agent_id="any", runtime={})
    cc, qp = await _resolve_model_queue_context(
        db,  # type: ignore[arg-type]
        rs,  # type: ignore[arg-type]
        None,
    )
    assert cc == "privileged"
    assert qp == 10


@pytest.mark.asyncio
async def test_runtime_queue_priority_override():
    db = _Session(False)  # type: ignore[arg-type]
    rs = SimpleNamespace(agent_id="", runtime={"queue_priority": 7})
    cc, qp = await _resolve_model_queue_context(
        db,  # type: ignore[arg-type]
        rs,  # type: ignore[arg-type]
        None,
    )
    assert cc == "interactive"
    assert qp == 7
