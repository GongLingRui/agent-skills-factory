"""Declarative workflow steps on RunSpec runtime (docs/14 P3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

StepType = Literal["kb_search", "model_turn", "tool_call", "output_schema"]


@dataclass
class WorkflowStep:
    id: str
    type: StepType
    params: dict[str, Any]


def parse_workflow(runtime: dict[str, Any] | None) -> list[WorkflowStep] | None:
    if not runtime or not isinstance(runtime, dict):
        return None
    wf = runtime.get("workflow")
    if not isinstance(wf, dict):
        return None
    steps_raw = wf.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        return None
    steps: list[WorkflowStep] = []
    for item in steps_raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        stype = str(item.get("type") or "model_turn").strip()
        if not sid:
            continue
        if stype not in ("kb_search", "model_turn", "tool_call", "output_schema"):
            stype = "model_turn"
        params = item.get("params")
        steps.append(
            WorkflowStep(
                id=sid,
                type=stype,  # type: ignore[arg-type]
                params=params if isinstance(params, dict) else {},
            )
        )
    return steps or None


def workflow_state(runtime: dict[str, Any] | None) -> dict[str, Any]:
    if not runtime or not isinstance(runtime, dict):
        return {"current_index": 0, "completed": []}
    wf = runtime.get("workflow")
    if not isinstance(wf, dict):
        return {"current_index": 0, "completed": []}
    st = wf.get("state")
    if isinstance(st, dict):
        return st
    return {"current_index": 0, "completed": []}


def build_workflow_from_enterprise(
    merged_enterprise: dict[str, Any] | None,
    *,
    enabled: bool,
) -> dict[str, Any] | None:
    if not enabled:
        return None
    ent = merged_enterprise if isinstance(merged_enterprise, dict) else {}
    wf = ent.get("workflow")
    if not isinstance(wf, dict):
        return None
    steps = wf.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    return {
        "steps": steps,
        "state": {"current_index": 0, "completed": []},
    }
