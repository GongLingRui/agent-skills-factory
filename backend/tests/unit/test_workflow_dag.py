"""Tests for workflow DAG parsing."""

from __future__ import annotations

from agent_factory.core.workflow_dag import (
    build_workflow_from_enterprise,
    parse_workflow,
)


def test_parse_workflow_steps():
    rt = {
        "workflow": {
            "steps": [
                {"id": "s1", "type": "kb_search", "params": {"query_from": "user"}},
                {"id": "s2", "type": "model_turn"},
            ],
            "state": {"current_index": 0, "completed": []},
        }
    }
    steps = parse_workflow(rt)
    assert steps is not None
    assert len(steps) == 2
    assert steps[0].type == "kb_search"


def test_build_workflow_from_enterprise():
    ent = {"workflow": {"steps": [{"id": "a", "type": "model_turn"}]}}
    wf = build_workflow_from_enterprise(ent, enabled=True)
    assert wf is not None
    assert wf["state"]["current_index"] == 0
