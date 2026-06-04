"""Execute workflow DAG steps until ``model_turn`` (docs/14 P3)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.core.workflow_dag import (
    WorkflowStep,
    parse_workflow,
    workflow_state,
)
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.db.models.run_spec import RunSpec
from agent_factory.services.degradation_runtime import DegradationRunKnobs
from agent_factory.services.tool_gateway import ToolGateway
from agent_factory.services.workflow_state_store import persist_workflow_state

logger = logging.getLogger(__name__)


@dataclass
class WorkflowExecutionResult:
    extra_messages: list[dict[str, Any]]
    runtime: dict[str, Any]
    stopped_at_model_turn: bool


def _msg(role: str, content: str) -> dict[str, Any]:
    return {"role": role, "content": content}


async def execute_workflow_until_model_turn(
    db: AsyncSession,
    *,
    tool_gateway: ToolGateway,
    run_spec: RunSpec,
    session: ChatSession,
    runtime: dict[str, Any],
    user_message: str,
    eff_allowed: list[str],
    caller_permissions: frozenset[str] | None,
    degradation_knobs: DegradationRunKnobs | None,
) -> WorkflowExecutionResult:
    """Run kb_search / tool_call steps; persist index after each step."""
    steps = parse_workflow(runtime)
    if not steps:
        return WorkflowExecutionResult([], runtime, False)

    st = dict(workflow_state(runtime))
    idx = int(st.get("current_index", 0))
    completed: list[str] = list(st.get("completed") or [])
    extras: list[dict[str, Any]] = []

    while idx < len(steps):
        step: WorkflowStep = steps[idx]
        if step.type == "model_turn":
            break
        if step.type == "output_schema":
            completed.append(step.id)
            idx += 1
            continue
        if step.type == "kb_search":
            if "kb.search" not in eff_allowed:
                idx += 1
                continue
            q = user_message
            if step.params.get("query"):
                q = str(step.params["query"])
            try:
                kb_out = await tool_gateway.validate_and_run_async(
                    db,
                    tool_id="kb.search",
                    params={"query": q},
                    allowed_tools=eff_allowed,
                    retrieval_scopes=run_spec.retrieval_scopes or [],
                    department=session.department,
                    run_spec=run_spec,
                    caller_permissions=caller_permissions,
                    degradation_knobs=degradation_knobs,
                )
                snippet = json.dumps(kb_out, ensure_ascii=False)[:4000]
                extras.append(
                    _msg(
                        "user",
                        f"[workflow:{step.id}] kb.search：{snippet}",
                    )
                )
            except Exception:
                logger.exception("workflow step kb_search failed id=%s", step.id)
            completed.append(step.id)
            idx += 1
        elif step.type == "tool_call":
            tool_id = str(step.params.get("tool_id") or "").strip()
            params = step.params.get("params")
            if not tool_id or tool_id not in eff_allowed:
                idx += 1
                continue
            if not isinstance(params, dict):
                params = {}
            try:
                out = await tool_gateway.validate_and_run_async(
                    db,
                    tool_id=tool_id,
                    params=params,
                    allowed_tools=eff_allowed,
                    retrieval_scopes=run_spec.retrieval_scopes or [],
                    department=session.department,
                    run_spec=run_spec,
                    caller_permissions=caller_permissions,
                    degradation_knobs=degradation_knobs,
                )
                snippet = json.dumps(out, ensure_ascii=False)[:3000]
                extras.append(
                    _msg("user", f"[workflow:{step.id}] {tool_id}：{snippet}")
                )
            except Exception:
                logger.exception(
                    "workflow tool_call failed id=%s tool=%s",
                    step.id,
                    tool_id,
                )
            completed.append(step.id)
            idx += 1
        else:
            idx += 1

        new_state = {
            "current_index": idx,
            "completed": completed,
            "last_step_id": step.id,
        }
        runtime = await persist_workflow_state(
            db,
            run_id=run_spec.run_id,
            runtime=runtime,
            state=new_state,
        )

    stopped = idx < len(steps) and steps[idx].type == "model_turn"
    return WorkflowExecutionResult(extras, runtime, stopped)
