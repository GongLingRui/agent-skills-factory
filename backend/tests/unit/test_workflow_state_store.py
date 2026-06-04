"""Tests for workflow state persistence helpers."""

from __future__ import annotations

from agent_factory.core.workflow_dag import workflow_state
from agent_factory.services.workflow_state_store import merge_workflow_state


def test_merge_workflow_state():
    rt = {"model": "m", "workflow": {"steps": [{"id": "s1"}]}}
    st = {"current_index": 2, "completed": ["s1", "s2"]}
    merged = merge_workflow_state(rt, st)
    assert merged["workflow"]["state"]["current_index"] == 2
    assert workflow_state(merged)["completed"] == ["s1", "s2"]
