"""Tests for tool loop message consistency and intermediate checkpoints."""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_factory.services.runner_service import RunnerService


_PATCHES: list[Any] = [
    patch(
        "agent_factory.services.runner_service.build_tools_for_chat_api",
        new=AsyncMock(return_value=[]),
    ),
    patch(
        "agent_factory.services.runner_service.prepare_messages_for_chat_api",
        new=AsyncMock(side_effect=lambda m, *a, **k: list(m)),
    ),
    patch(
        "agent_factory.services.runner_service.maybe_compact_tool_messages",
        new=AsyncMock(),
    ),
    patch(
        "agent_factory.services.runner_service.apply_post_sampling_hooks",
        side_effect=lambda t, rs: t,
    ),
    patch(
        "agent_factory.services.runner_service.output_matches_json_constraint",
        return_value=None,
    ),
    patch(
        "agent_factory.services.runner_service.SessionMemoryExtractor",
        return_value=MagicMock(should_extract=lambda *a, **k: False),
    ),
    patch(
        "agent_factory.services.runner_service.roll_forward_cross_session_memory",
        new=AsyncMock(),
    ),
    patch(
        "agent_factory.services.runner_service.fetch_cross_session_summary",
        new=AsyncMock(return_value=None),
    ),
    patch(
        "agent_factory.services.runner_service.load_latest_session_memory",
        new=AsyncMock(return_value=None),
    ),
    patch(
        "agent_factory.services.runner_service.inject_session_memory_into_system",
        side_effect=lambda s, m: s,
    ),
    patch(
        "agent_factory.services.runner_service._resolve_model_queue_context",
        new=AsyncMock(return_value=("interactive", 5)),
    ),
    patch.object(
        RunnerService,
        "_skill_package_metadata",
        new=AsyncMock(return_value=None),
    ),
    patch(
        "agent_factory.services.runner_service.load_workflow_runtime",
        new=AsyncMock(side_effect=lambda _db, _rid, fallback_runtime=None: dict(fallback_runtime or {})),
    ),
    patch(
        "agent_factory.services.runner_service.execute_workflow_until_model_turn",
        new=AsyncMock(
            return_value=type(
                "WfR",
                (),
                {
                    "extra_messages": [],
                    "runtime": {},
                    "stopped_at_model_turn": False,
                },
            )()
        ),
    ),
]


@contextlib.contextmanager
def _runner_patches():
    with contextlib.ExitStack() as stack:
        for p in _PATCHES:
            stack.enter_context(p)
        yield


def _run_spec():
    rs = MagicMock()
    rs.runspec_schema_version = 1
    rs.runtime = {}
    rs.allowed_tools = ["t1", "t2"]
    rs.prompt_parts = [{"content": "sys"}]
    rs.output_schema = None
    rs.retrieval_scopes = []
    rs.run_id = "run_1"
    rs.agent_id = "agent_1"
    return rs


def _session():
    s = MagicMock()
    s.run_id = "run_1"
    s.session_id = "sess_1"
    s.user_id_hash = "u1"
    s.agent_id = "agent_1"
    s.department = "dept1"
    s.turn_count = 0
    return s


def _chunk(delta="", finish=None, tcalls=None, usage=None):
    c = MagicMock()
    c.choices = [MagicMock(delta=delta, finish_reason=finish, tool_calls=tcalls)]
    c.usage = usage
    return c


@pytest.mark.asyncio
async def test_messages_contains_tool_roles_after_two_tool_loop():
    """After a turn with 2 tool calls, messages must contain tool roles."""
    import copy

    mgw = MagicMock()
    tgw = MagicMock()
    svc = RunnerService(mgw, tgw)

    svc._load_history = AsyncMock(return_value=([], None))
    svc._preload_doc_extract_for_uploads = AsyncMock(return_value="")

    # Capture deep copies of messages at each checkpoint to avoid mutable-reference issues
    captured: list[list[dict[str, Any]]] = []

    async def _capture_save(db, run_spec, session, messages, turn, session_memory=None, last_summarized_message_index=None):
        captured.append(copy.deepcopy(messages))

    svc._save_checkpoint = AsyncMock(side_effect=_capture_save)

    async def _chat1(**kw):
        yield _chunk(delta="ok", finish=None)
        yield _chunk(
            delta="",
            finish="tool_calls",
            tcalls=[
                {
                    "id": "c1",
                    "function": {"name": "t1", "arguments": "{}"},
                },
                {
                    "id": "c2",
                    "function": {"name": "t2", "arguments": "{}"},
                },
            ],
            usage={"total_tokens": 10},
        )

    async def _chat2(**kw):
        yield _chunk(delta="done", finish="stop", usage={"total_tokens": 20})

    mgw.chat.side_effect = [_chat1(), _chat2()]
    tgw.validate_and_run_async = AsyncMock(
        side_effect=[
            {"result": "r1"},
            {"result": "r2"},
        ]
    )

    with _runner_patches():
        events = []
        async for ev in svc.run_turn(
            db=MagicMock(),
            run_spec=_run_spec(),
            session=_session(),
            user_message="hi",
        ):
            events.append(ev)

    # pending + 2 intermediate + final = at least 4
    assert len(captured) >= 4

    # Final checkpoint
    final_messages = captured[-1]
    roles = [m["role"] for m in final_messages]
    assert roles == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]

    # Verify tool messages
    tool_msgs = [m for m in final_messages if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert tool_msgs[0]["tool_call_id"] == "c1"
    assert tool_msgs[1]["tool_call_id"] == "c2"

    # Verify intermediate checkpoint after first tool
    # captured[0]: pending
    # captured[1]: after tool1
    # captured[2]: after tool2
    # captured[3]: final
    mid_msgs = captured[2]
    mid_roles = [m["role"] for m in mid_msgs]
    assert mid_roles == ["user", "assistant", "tool", "assistant", "tool"]


@pytest.mark.asyncio
async def test_intermediate_checkpoint_preserved_on_crash_after_first_tool():
    """If runner crashes after first tool, intermediate checkpoint exists."""
    import copy

    mgw = MagicMock()
    tgw = MagicMock()
    svc = RunnerService(mgw, tgw)

    svc._load_history = AsyncMock(return_value=([], None))
    svc._preload_doc_extract_for_uploads = AsyncMock(return_value="")

    captured: list[list[dict[str, Any]]] = []

    async def _capture_save(db, run_spec, session, messages, turn, session_memory=None, last_summarized_message_index=None):
        captured.append(copy.deepcopy(messages))

    svc._save_checkpoint = AsyncMock(side_effect=_capture_save)

    async def _chat1(**kw):
        yield _chunk(
            delta="",
            finish="tool_calls",
            tcalls=[
                {
                    "id": "c1",
                    "function": {"name": "t1", "arguments": "{}"},
                },
            ],
            usage={"total_tokens": 10},
        )

    mgw.chat.side_effect = [_chat1(), Exception("boom")]
    tgw.validate_and_run_async = AsyncMock(return_value={"result": "r1"})

    with _runner_patches():
        events = []
        async for ev in svc.run_turn(
            db=MagicMock(),
            run_spec=_run_spec(),
            session=_session(),
            user_message="hi",
        ):
            events.append(ev)

    # pending + 1 intermediate
    assert len(captured) >= 2

    # Intermediate checkpoint should contain user + assistant(tool_calls) + tool
    mid_msgs = captured[1]
    mid_roles = [m["role"] for m in mid_msgs]
    assert mid_roles == ["user", "assistant", "tool"]

    # Should have yielded an error event for the second model call
    assert any(e.get("type") == "error" for e in events)
