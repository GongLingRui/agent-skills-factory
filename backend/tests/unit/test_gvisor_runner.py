"""Tests for gVisor script worker dispatch."""

from __future__ import annotations

from unittest.mock import patch

from agent_factory.workers.gvisor_runner import gvisor_available
from agent_factory.workers.script_worker import (
    resolve_script_worker_runtime,
    run_controlled_script,
)


def test_resolve_auto_prefers_gvisor_when_runsc_present():
    with patch(
        "agent_factory.workers.script_worker.gvisor_available",
        return_value=True,
    ):
        assert resolve_script_worker_runtime("auto") == "gvisor"


def test_resolve_auto_subprocess_without_runsc():
    with patch(
        "agent_factory.workers.script_worker.gvisor_available",
        return_value=False,
    ):
        assert resolve_script_worker_runtime("auto") == "subprocess"


def test_gvisor_available_false_without_binary():
    with patch(
        "agent_factory.workers.gvisor_runner.resolve_runsc_binary",
        return_value=None,
    ):
        assert gvisor_available() is False


def test_subprocess_runtime_still_works():
    source = "output = {'ok': True}"
    out = run_controlled_script(
        script_source=source,
        hook_id="t",
        input_payload={},
        worker_runtime="subprocess",
    )
    assert out.get("ok") is True
