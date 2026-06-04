"""Agent Runner: tool loop, SSE pump, checkpointing (docs/08, docs/34)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.core.context_memory import ContextMemorySettings
from agent_factory.core.minimax_tool_xml import (
    MinimaxStreamYieldController,
    parse_embedded_tool_calls,
)
from agent_factory.core.model_output_parse import output_matches_json_constraint
from agent_factory.core.post_sampling_hooks import apply_post_sampling_hooks
from agent_factory.core.runspec_schema import assert_runner_supports_runspec_version
from agent_factory.core.runspec_v2 import apply_v2_runtime_overrides
from agent_factory.db.models.skill import Skill
from agent_factory.core.session_memory_schema import SessionMemory
from agent_factory.core.tool_message_integrity import repair_missing_tool_results
from agent_factory.core.tool_schema import build_tools_for_chat_api
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.db.models.checkpoint import Checkpoint
from agent_factory.db.models.run_spec import RunSpec
from agent_factory.infra.minio_client import MinioClient
from agent_factory.infra.model_client import PromptTooLongError
from agent_factory.infra.model_queue import ModelQueuePolicyError
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.conversation_memory import (
    maybe_compact_tool_messages,
    prepare_messages_for_chat_api,
    tool_result_payload_for_api,
)
from agent_factory.services.degradation_runtime import DegradationRunKnobs
from agent_factory.services.model_gateway import ModelGateway
from agent_factory.services.session_memory import (
    SessionMemoryExtractor,
    inject_session_memory_into_system,
    load_latest_session_memory,
)
from agent_factory.services.tool_gateway import ToolGateway
from agent_factory.services.tool_result_persistence import (
    is_tool_result_stub,
    load_tool_result_from_persistence,
    make_tool_result_stub,
    parse_tool_result_stub,
    persist_large_tool_result,
    should_persist_tool_result,
)
from agent_factory.services.tool_use_summary import generate_tool_use_summary
from agent_factory.services.transcript_service import record_event
from agent_factory.services.user_agent_memory_service import (
    fetch_cross_session_summary,
    roll_forward_cross_session_memory,
)
from agent_factory.config import get_settings
from agent_factory.services.script_runner_service import run_script_hooks_phase
from agent_factory.services.workflow_executor import execute_workflow_until_model_turn
from agent_factory.services.workflow_state_store import load_workflow_runtime

logger = logging.getLogger(__name__)

_USAGE_WARN_RATIO = 0.85


def _usage_warning_message(
    usage: dict[str, int] | None,
    *,
    max_tokens: int,
) -> str | None:
    """Warn when reported tokens approach ``max_tokens`` (prd.md §7.5)."""
    if not usage or max_tokens <= 0:
        return None
    total = usage.get("total_tokens")
    if total is None:
        total = (usage.get("prompt_tokens") or 0) + (
            usage.get("completion_tokens") or 0
        )
    try:
        t = int(total)
    except (TypeError, ValueError):
        return None
    if t <= 0:
        return None
    if t >= int(max_tokens * _USAGE_WARN_RATIO):
        return "会话上下文已接近上限，建议新开对话以免内容被截断。"
    return None


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


_QUEUE_VALID = frozenset(
    {"privileged", "interactive", "document", "batch"},
)


def _concurrency_class_for_turn(
    run_spec: RunSpec,
    file_ids: list[str] | None,
) -> str:
    """Map RunSpec + attachments to model queue class (docs/10)."""
    runtime = run_spec.runtime or {}
    raw = runtime.get("concurrency_class")
    if isinstance(raw, str) and raw in _QUEUE_VALID:
        return raw
    if file_ids:
        return "document"
    return "interactive"


_DEFAULT_QUEUE_PRIORITY: dict[str, int] = {
    "privileged": 10,
    "interactive": 5,
    "document": 3,
    "batch": 1,
}


async def _resolve_model_queue_context(
    db: AsyncSession,
    run_spec: RunSpec,
    file_ids: list[str] | None,
) -> tuple[str, int]:
    """Privileged + priority 10 when ``degradation_exempt`` (docs/10, docs/13)."""
    aid = (run_spec.agent_id or "").strip()
    exempt = False
    if aid:
        r = await db.execute(
            select(AgentApp.degradation_exempt).where(AgentApp.id == aid),
        )
        cell = r.scalar_one_or_none()
        if cell is not None:
            exempt = bool(cell)
    runtime = run_spec.runtime or {}
    raw_pri = runtime.get("queue_priority")
    pri: int | None = None
    if isinstance(raw_pri, int) and 1 <= raw_pri <= 10:
        pri = raw_pri
    if exempt:
        cc = "privileged"
        qp = 10 if pri is None else max(10, pri)
        return cc, qp
    cc = _concurrency_class_for_turn(run_spec, file_ids)
    if pri is not None:
        return cc, pri
    return cc, _DEFAULT_QUEUE_PRIORITY.get(cc, 5)


def _msg(role: str, content: str, **extra: Any) -> dict[str, Any]:
    return {"role": role, "content": content, **extra}


def _user_message_for_model_with_files(
    user_message: str,
    file_ids: list[str] | None,
    *,
    preloaded: str = "",
) -> str:
    """Model sees file_id + optional doc.extract excerpt (checkpoint stays plain)."""
    body = user_message
    if preloaded:
        body = f"{body}{preloaded}"
    ids = [str(x).strip() for x in (file_ids or []) if str(x).strip()]
    if not ids:
        return body
    joined = ", ".join(ids)
    if preloaded:
        hint = f"\n\n[附件] file_id: {joined}（上文含服务端预读节选）"
    else:
        hint = (
            "\n\n[附件] 用户本回合已上传文件；请先使用 doc.extract 工具"
            f"（参数 file_id）读取正文后再作答。file_id: {joined}"
        )
    return f"{body}{hint}"


_MAX_ATTACH_CONTEXT_CHARS = 28_000


class RunnerService:
    """Execute a chat turn with tool-use loop and SSE streaming."""

    def __init__(self, model_gateway: ModelGateway, tool_gateway: ToolGateway) -> None:
        self.model_gateway = model_gateway
        self.tool_gateway = tool_gateway

    async def _skill_package_metadata(
        self,
        db: AsyncSession,
        run_spec: RunSpec,
    ) -> dict[str, Any] | None:
        sid = run_spec.skill_id
        sver = run_spec.skill_version
        if not sid or not sver:
            return None
        q = await db.execute(
            select(Skill).where(Skill.id == sid, Skill.version == sver)
        )
        row = q.scalar_one_or_none()
        if row is None:
            return None
        meta = row.package_metadata
        return meta if isinstance(meta, dict) else None

    async def run_turn_background(
        self,
        *,
        db: AsyncSession,
        run_spec: RunSpec,
        session: ChatSession,
        user_message: str,
        file_ids: list[str] | None = None,
        caller_permissions: frozenset[str] | None = None,
        degradation_exempt: bool = False,
        allowed_tools_override: list[str] | None = None,
        degradation_knobs: DegradationRunKnobs | None = None,
    ) -> dict[str, Any]:
        """Non-blocking execution; collect all events into a result dict."""
        result: dict[str, Any] = {
            "output": "",
            "usage": None,
            "schema_valid": None,
            "tool_calls": [],
            "errors": [],
        }
        async for event in self.run_turn(
            db=db,
            run_spec=run_spec,
            session=session,
            user_message=user_message,
            file_ids=file_ids,
            caller_permissions=caller_permissions,
            degradation_exempt=degradation_exempt,
            allowed_tools_override=allowed_tools_override,
            degradation_knobs=degradation_knobs,
        ):
            etype = event.get("type")
            if etype == "done":
                result["output"] = event.get("output", "")
                result["usage"] = event.get("usage")
                result["schema_valid"] = event.get("schema_valid")
            elif etype == "tool_call":
                result["tool_calls"].append(
                    {
                        "tool_id": event.get("tool_id"),
                        "status": event.get("status"),
                    }
                )
            elif etype == "error":
                result["errors"].append(
                    {
                        "code": event.get("code"),
                        "message": event.get("message"),
                    }
                )
        return result

    async def _preload_doc_extract_for_uploads(
        self,
        db: AsyncSession,
        *,
        file_ids: list[str] | None,
        eff_allowed: list[str],
        run_spec: RunSpec,
        session: ChatSession,
        caller_permissions: frozenset[str] | None,
    ) -> str:
        """Eager doc.extract so the model sees text while chat API uses tools=None."""
        if not file_ids or "doc.extract" not in eff_allowed:
            return ""
        parts: list[str] = []
        budget = _MAX_ATTACH_CONTEXT_CHARS
        for raw in file_ids:
            fid = str(raw).strip()
            if not fid or budget <= 0:
                break
            try:
                res = await self.tool_gateway.validate_and_run_async(
                    db,
                    tool_id="doc.extract",
                    params={"file_id": fid},
                    allowed_tools=eff_allowed,
                    retrieval_scopes=run_spec.retrieval_scopes or [],
                    department=session.department,
                    run_spec=run_spec,
                    caller_permissions=caller_permissions,
                )
                text = str(res.get("text") or "")
            except AgentFactoryException as exc:
                text = f"[doc.extract 不可用: {exc.code}]"
            block = f"【{fid}】\n{text}"
            if len(block) > budget:
                block = block[: max(0, budget - 1)] + "…"
            parts.append(block)
            budget -= len(block) + 2
        if not parts:
            return ""
        return (
            "\n\n--- 以下为附件正文（服务端 doc.extract 预读，节选）---\n"
            + "\n\n".join(parts)
        )

    async def run_turn(
        self,
        *,
        db: AsyncSession,
        run_spec: RunSpec,
        session: ChatSession,
        user_message: str,
        file_ids: list[str] | None = None,
        caller_permissions: frozenset[str] | None = None,
        degradation_exempt: bool = False,
        allowed_tools_override: list[str] | None = None,
        degradation_knobs: DegradationRunKnobs | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield SSE event dicts."""
        from agent_factory.utils.query_profiler import QueryProfiler

        profiler = QueryProfiler(
            run_id=run_spec.run_id,
            session_id=session.session_id,
            turn_number=(session.turn_count or 0) + 1,
        )
        profiler.checkpoint("user_input_received")

        messages, last_summarized_index = await self._load_history(db, session)
        profiler.checkpoint("load_history")

        settings = get_settings()
        turn_user_message = user_message
        if settings.SCRIPT_HOOKS_ENABLED and run_spec.script_hooks:
            try:
                pre = await run_script_hooks_phase(
                    db,
                    run_spec=run_spec,
                    phase="preprocess",
                    input_payload={
                        "user_message": turn_user_message,
                        "file_ids": list(file_ids or []),
                    },
                )
                if isinstance(pre.get("user_message"), str):
                    turn_user_message = pre["user_message"]
            except AgentFactoryException:
                raise
            except Exception:
                logger.exception("script_preprocess_skipped")

        from agent_factory.core.conversation_continue import enrich_continue_user_message

        turn_user_message = enrich_continue_user_message(messages, turn_user_message)
        messages.append(_msg("user", turn_user_message))

        rsv = int(run_spec.runspec_schema_version or 1)
        assert_runner_supports_runspec_version(rsv)
        if rsv >= 2:
            logger.info(
                "RunSpec runspec_schema_version=%s: Runner v2 path (backward "
                "compatible with v1 core semantics)",
                rsv,
            )

        runtime = await load_workflow_runtime(
            db,
            run_spec.run_id,
            fallback_runtime=run_spec.runtime,
        )
        runtime = apply_v2_runtime_overrides(
            runtime,
            runspec_schema_version=rsv,
        )
        run_spec.runtime = runtime
        max_turns = int(runtime.get("max_turns", 6))
        model = str(runtime.get("model", "MiniMax-M2.7"))
        max_tokens = runtime.get("max_tokens", 8000)

        if degradation_knobs is not None and not degradation_exempt:
            if degradation_knobs.max_turns_cap is not None:
                max_turns = min(max_turns, degradation_knobs.max_turns_cap)
            if degradation_knobs.model_override:
                model = degradation_knobs.model_override

        eff_allowed = (
            allowed_tools_override
            if allowed_tools_override is not None
            else (run_spec.allowed_tools or [])
        )

        # 无用户附件时不暴露 doc.extract，避免模型误把 read_reference 当附件读取
        if not file_ids:
            eff_allowed = [t for t in eff_allowed if t != "doc.extract"]

        from agent_factory.core.read_reference import collect_lazy_reference_names

        lazy_ref_names = collect_lazy_reference_names(run_spec.lazy_references)
        tools_for_api = await build_tools_for_chat_api(
            db,
            eff_allowed,
            lazy_reference_names=lazy_ref_names or None,
        )

        if settings.WORKFLOW_DAG_ENABLED:
            wf_result = await execute_workflow_until_model_turn(
                db,
                tool_gateway=self.tool_gateway,
                run_spec=run_spec,
                session=session,
                runtime=runtime,
                user_message=turn_user_message,
                eff_allowed=eff_allowed,
                caller_permissions=caller_permissions,
                degradation_knobs=degradation_knobs,
            )
            runtime = wf_result.runtime
            run_spec.runtime = runtime
            for wm in wf_result.extra_messages:
                messages.append(wm)

        preload = await self._preload_doc_extract_for_uploads(
            db,
            file_ids=file_ids,
            eff_allowed=eff_allowed,
            run_spec=run_spec,
            session=session,
            caller_permissions=caller_permissions,
        )

        ctx_cfg = ContextMemorySettings.from_runtime(runtime)
        cc, qp = await _resolve_model_queue_context(db, run_spec, file_ids)

        # Build system prompt from prompt_parts
        system_content = "\n\n".join(
            p.get("content", "")
            for p in (run_spec.prompt_parts or [])
            if isinstance(p, dict)
        )

        # Memory pre-fetch: try session runtime_context first
        existing_session_memory: SessionMemory | None = None
        prefetched_xs: str | None = None
        rtc = session.runtime_context if isinstance(session.runtime_context, dict) else {}
        if rtc:
            try:
                mem_raw = rtc.get("session_memory")
                if isinstance(mem_raw, dict):
                    existing_session_memory = SessionMemory(**mem_raw)
                xs_raw = rtc.get("cross_session_summary")
                if isinstance(xs_raw, str):
                    prefetched_xs = xs_raw
            except Exception:
                logger.warning("session_runtime_context_parse_failed")

        if prefetched_xs is None:
            prefetched_xs = await fetch_cross_session_summary(
                db,
                user_id_hash=session.user_id_hash,
                agent_id=session.agent_id or run_spec.agent_id,
            )
        if (
            prefetched_xs
            and ctx_cfg.enabled
            and ctx_cfg.cross_session_memory_enabled
        ):
            system_content += "\n\n## 跨会话记忆（自动摘要）\n" + prefetched_xs

        if existing_session_memory is None and session.run_id:
            existing_session_memory = await load_latest_session_memory(db, session.run_id)

        system_content = inject_session_memory_into_system(
            system_content, existing_session_memory
        )
        profiler.checkpoint("build_system_prompt")

        # Pending checkpoint: protect user message before any model call
        next_turn = (session.turn_count or 0) + 1
        await self._save_checkpoint(
            db, run_spec, session, messages, next_turn
        )

        turn = 0
        message_id = f"msg_{uuid.uuid4().hex[:8]}"
        schema_retry_hint: dict[str, Any] | None = None
        reactive_compact_used = False
        output_recovery_count = 0
        consecutive_compact_failures = 0

        from agent_factory.core.denial_tracking import DenialTracker

        denial_tracker = DenialTracker(max_consecutive=3, max_total=20)

        while turn < max_turns:
            turn += 1
            assistant_text = ""
            tool_calls_buffer: list[dict[str, Any]] = []
            last_usage: dict[str, int] | None = None
            finish_reason: str | None = None

            # Build api_messages dynamically from messages each iteration
            msgs_for_model = list(messages)
            if file_ids or preload:
                user_idx = [
                    i
                    for i, m in enumerate(msgs_for_model)
                    if m.get("role") == "user"
                ]
                if user_idx:
                    msgs_for_model[user_idx[-1]] = _msg(
                        "user",
                        _user_message_for_model_with_files(
                            user_message,
                            file_ids,
                            preloaded=preload,
                        ),
                    )

            try:
                msgs_for_model = await prepare_messages_for_chat_api(
                    msgs_for_model,
                    ctx_cfg,
                    self.model_gateway,
                    main_model=model,
                )
            except Exception:
                logger.exception("prepare_messages_failed_emergency_snip")
                from agent_factory.core.context_memory import apply_history_snip

                msgs_for_model = apply_history_snip(msgs_for_model, ctx_cfg)

            await maybe_compact_tool_messages(
                msgs_for_model,
                ctx_cfg,
                self.model_gateway,
                main_model=model,
            )

            # Repair missing tool results
            msgs_for_model = repair_missing_tool_results(msgs_for_model)
            profiler.checkpoint("prepare_messages")

            api_messages: list[dict[str, Any]] = [
                _msg("system", system_content),
                *msgs_for_model,
            ]
            if schema_retry_hint is not None:
                api_messages.append(schema_retry_hint)

            # Tool Use Summary injection (if previous turn had >=2 tool calls)
            tool_calls_executed_count = sum(
                1 for m in messages if m.get("role") == "assistant" and m.get("tool_calls")
            )
            # Actually we want count of tool calls in the *last* assistant message
            last_assistant = None
            for m in reversed(messages):
                if m.get("role") == "assistant" and m.get("tool_calls"):
                    last_assistant = m
                    break
            if last_assistant and len(last_assistant.get("tool_calls", [])) >= 2:
                # Generate summary from last turn's tool results
                tc_list = last_assistant.get("tool_calls", [])
                tr_list = []
                for tc in tc_list:
                    tcid = tc.get("id", "")
                    for mm in messages:
                        if mm.get("role") == "tool" and mm.get("tool_call_id") == tcid:
                            tr_list.append({
                                "tool_id": tc.get("function", {}).get("name", ""),
                                "call_id": tcid,
                                "result_preview": str(mm.get("content", ""))[:400],
                            })
                            break
                if tr_list:
                    summary = await generate_tool_use_summary(
                        self.model_gateway,
                        model=model,
                        tool_results=tr_list,
                        max_tokens=256,
                    )
                    if summary:
                        api_messages.append(
                            _msg("system", "[Tool Use Summary]\n" + summary)
                        )

            # Proactive auto-compact: if estimated tokens approach the limit,
            # snip history before the model call to avoid reactive PTL.
            est_chars = sum(
                len(str(m.get("content", ""))) for m in api_messages
            )
            est_tokens = est_chars // max(1, ctx_cfg.chars_per_token_estimate)
            proactive_threshold = int(max_tokens * 0.75)
            if (
                ctx_cfg.enabled
                and est_tokens > proactive_threshold
                and consecutive_compact_failures < 3
            ):
                logger.info(
                    "proactive_auto_compact_triggered",
                    extra={
                        "est_tokens": est_tokens,
                        "threshold": proactive_threshold,
                        "consecutive_compact_failures": consecutive_compact_failures,
                    },
                )
                from agent_factory.core.context_memory import apply_history_snip

                proactive_cfg = ContextMemorySettings(
                    enabled=ctx_cfg.enabled,
                    compression=ctx_cfg.compression,
                    cross_session_memory_enabled=ctx_cfg.cross_session_memory_enabled,
                    keep_recent_user_turns=max(
                        2, ctx_cfg.keep_recent_user_turns
                    ),
                    min_user_turns=max(1, ctx_cfg.min_user_turns),
                    history_budget_chars=ctx_cfg.history_budget_chars,
                    summary_max_output_tokens=ctx_cfg.summary_max_output_tokens,
                    summarization_model=ctx_cfg.summarization_model,
                    summarize_input_cap_chars=ctx_cfg.summarize_input_cap_chars,
                    max_shrink_rounds=ctx_cfg.max_shrink_rounds,
                    tool_compression=ctx_cfg.tool_compression,
                    tool_result_max_chars=ctx_cfg.tool_result_max_chars,
                    tool_result_head_chars=ctx_cfg.tool_result_head_chars,
                    tool_result_tail_chars=ctx_cfg.tool_result_tail_chars,
                    chars_per_token_estimate=ctx_cfg.chars_per_token_estimate,
                )
                msgs_for_model = apply_history_snip(
                    msgs_for_model, proactive_cfg
                )
                api_messages = [
                    _msg("system", system_content),
                    *msgs_for_model,
                ]
                if schema_retry_hint is not None:
                    api_messages.append(schema_retry_hint)
                consecutive_compact_failures += 1

            mm_stream = MinimaxStreamYieldController()
            model_call_failed = False
            try:
                await record_event(
                    db,
                    run_id=run_spec.run_id,
                    session_id=session.session_id,
                    turn_number=next_turn,
                    event_type="model_call_start",
                    payload={"turn": turn, "message_id": message_id},
                )
                profiler.checkpoint("model_call_start")
                first_chunk_seen = False
                async for chunk in self.model_gateway.chat(
                    model=model,
                    messages=api_messages,
                    max_tokens=max_tokens,
                    temperature=0.7,
                    tools=tools_for_api,
                    concurrency_class=cc,
                    queue_priority=qp,
                ):
                    if not first_chunk_seen:
                        first_chunk_seen = True
                        profiler.checkpoint("first_chunk_received")
                    if chunk.usage:
                        last_usage = dict(chunk.usage)
                    for choice in chunk.choices:
                        delta = choice.delta
                        finish = choice.finish_reason
                        tcalls = choice.tool_calls

                        if delta:
                            assistant_text += delta
                            piece = mm_stream.on_delta(assistant_text)
                            if piece:
                                yield {
                                    "type": "text",
                                    "delta": piece,
                                    "message_id": message_id,
                                }

                        if tcalls:
                            for tc in tcalls:
                                # OpenAI-style streaming: tool_calls arrive in
                                # partial chunks keyed by ``index``.  Merge
                                # ``function.arguments`` strings instead of
                                # blindly appending duplicates.
                                if "index" in tc:
                                    idx = tc["index"]
                                    if idx >= len(tool_calls_buffer):
                                        while len(tool_calls_buffer) <= idx:
                                            tool_calls_buffer.append({})
                                    entry = tool_calls_buffer[idx]
                                    if tc.get("id"):
                                        entry["id"] = tc["id"]
                                    if tc.get("type"):
                                        entry["type"] = tc["type"]
                                    func = tc.get("function", {})
                                    if func:
                                        if "function" not in entry:
                                            entry["function"] = {}
                                        if func.get("name"):
                                            entry["function"]["name"] = func["name"]
                                        if func.get("arguments"):
                                            entry["function"]["arguments"] = (
                                                entry["function"].get("arguments", "")
                                                + func["arguments"]
                                            )
                                    yield {
                                        "type": "tool_call",
                                        "tool_id": entry.get("function", {}).get("name", ""),
                                        "call_id": entry.get("id", ""),
                                        "status": "running",
                                    }
                                else:
                                    # Non-streaming / complete tool call (e.g. test mocks)
                                    tool_calls_buffer.append(tc)
                                    yield {
                                        "type": "tool_call",
                                        "tool_id": tc.get("function", {}).get("name", ""),
                                        "call_id": tc.get("id", ""),
                                        "status": "running",
                                    }

                        if finish:
                            finish_reason = finish
                            break
                tail_piece = mm_stream.flush_end(assistant_text)
                if tail_piece:
                    yield {
                        "type": "text",
                        "delta": tail_piece,
                        "message_id": message_id,
                    }
                embedded = parse_embedded_tool_calls(assistant_text)
                if embedded and not tool_calls_buffer:
                    tool_calls_buffer.extend(embedded)
                await record_event(
                    db,
                    run_id=run_spec.run_id,
                    session_id=session.session_id,
                    turn_number=next_turn,
                    event_type="model_call_end",
                    payload={"turn": turn, "finish_reason": finish_reason, "message_id": message_id},
                )
                # Successful model call resets compact failure counter
                consecutive_compact_failures = 0
            except PromptTooLongError as exc:
                model_call_failed = True
                await record_event(
                    db,
                    run_id=run_spec.run_id,
                    session_id=session.session_id,
                    turn_number=next_turn,
                    event_type="error",
                    payload={"turn": turn, "code": "PROMPT_TOO_LONG", "message": str(exc)},
                )
                consecutive_compact_failures += 1
                if consecutive_compact_failures >= 3:
                    yield {
                        "type": "error",
                        "code": "PROMPT_TOO_LONG",
                        "message": "连续多次上下文压缩失败，请缩短输入或新开对话",
                    }
                    return
                if not reactive_compact_used:
                    reactive_compact_used = True
                    from agent_factory.core.context_memory import apply_history_snip

                    emergency_keep = max(1, ctx_cfg.keep_recent_user_turns // 2)
                    emergency_cfg = ContextMemorySettings(
                        enabled=ctx_cfg.enabled,
                        compression=ctx_cfg.compression,
                        cross_session_memory_enabled=ctx_cfg.cross_session_memory_enabled,
                        keep_recent_user_turns=emergency_keep,
                        min_user_turns=max(1, ctx_cfg.min_user_turns),
                        history_budget_chars=ctx_cfg.history_budget_chars,
                        summary_max_output_tokens=ctx_cfg.summary_max_output_tokens,
                        summarization_model=ctx_cfg.summarization_model,
                        summarize_input_cap_chars=ctx_cfg.summarize_input_cap_chars,
                        max_shrink_rounds=ctx_cfg.max_shrink_rounds,
                        tool_compression=ctx_cfg.tool_compression,
                        tool_result_max_chars=ctx_cfg.tool_result_max_chars,
                        tool_result_head_chars=ctx_cfg.tool_result_head_chars,
                        tool_result_tail_chars=ctx_cfg.tool_result_tail_chars,
                        chars_per_token_estimate=ctx_cfg.chars_per_token_estimate,
                    )
                    messages = apply_history_snip(messages, emergency_cfg)
                    # Also re-snip the api_messages base
                    turn -= 1  # retry same turn number
                    continue
                yield {
                    "type": "error",
                    "code": "PROMPT_TOO_LONG",
                    "message": "输入上下文过长，已尝试压缩后仍无法处理",
                }
                return
            except ModelQueuePolicyError as exc:
                model_call_failed = True
                yield {
                    "type": "error",
                    "code": "MODEL_QUEUE_BUSY",
                    "message": "模型排队繁忙，请稍后重试",
                    "retry_after": exc.retry_after,
                }
                return
            except Exception:
                model_call_failed = True
                logger.exception("Model call failed")
                await record_event(
                    db,
                    run_id=run_spec.run_id,
                    session_id=session.session_id,
                    turn_number=next_turn,
                    event_type="error",
                    payload={"turn": turn, "code": "MODEL_UNAVAILABLE"},
                )
                yield {
                    "type": "error",
                    "code": "MODEL_UNAVAILABLE",
                    "message": "模型服务暂时不可用，请稍后重试",
                }
                return

            warn_msg = _usage_warning_message(last_usage, max_tokens=max_tokens)
            if warn_msg:
                yield {
                    "type": "usage_warning",
                    "code": "CONTEXT_NEAR_LIMIT",
                    "message": warn_msg,
                }

            # Max Output Tokens Recovery
            if finish_reason == "length" and output_recovery_count < 2 and not tool_calls_buffer:
                output_recovery_count += 1
                messages.append(_msg("assistant", assistant_text))
                messages.append(_msg("user", "请继续输出剩余内容。"))
                await record_event(
                    db,
                    run_id=run_spec.run_id,
                    session_id=session.session_id,
                    turn_number=next_turn,
                    event_type="model_call_end",
                    payload={"turn": turn, "recovery": True, "output_recovery_count": output_recovery_count},
                )
                turn -= 1  # do not consume a turn
                continue
            elif finish_reason == "length" and output_recovery_count >= 2:
                yield {
                    "type": "usage_warning",
                    "code": "OUTPUT_TRUNCATED",
                    "message": "模型输出因长度限制被截断，建议分步提问。",
                }

            # If no tool calls, we're done (with optional schema validation)
            if not tool_calls_buffer:
                assistant_safe = apply_post_sampling_hooks(assistant_text, run_spec)
                if settings.SCRIPT_HOOKS_ENABLED and run_spec.script_hooks:
                    try:
                        post = await run_script_hooks_phase(
                            db,
                            run_spec=run_spec,
                            phase="postprocess",
                            input_payload={
                                "output": assistant_safe,
                                "user_message": turn_user_message,
                            },
                        )
                        if isinstance(post.get("output"), str):
                            assistant_safe = post["output"]
                    except Exception:
                        logger.exception("script_postprocess_skipped")
                pkg_meta = await self._skill_package_metadata(db, run_spec)
                valid = output_matches_json_constraint(
                    assistant_safe,
                    schema_name=run_spec.output_schema,
                    agent_id=run_spec.agent_id,
                    package_metadata=pkg_meta,
                )
                if valid is False and turn < max_turns:
                    # Retry: add hint and continue loop
                    schema_retry_hint = _msg(
                        "user",
                        "请确保输出符合要求的 JSON Schema 格式。",
                    )
                    continue
                messages.append(_msg("assistant", assistant_safe))

                extractor = SessionMemoryExtractor(self.model_gateway)
                new_session_memory = existing_session_memory
                if extractor.should_extract(
                    turn,
                    messages,
                    existing_session_memory,
                    last_summarized_message_index=last_summarized_index,
                ):
                    extracted = await extractor.extract(
                        messages=messages,
                        model=model,
                        last_summarized_message_index=last_summarized_index,
                    )
                    if extracted:
                        new_session_memory = extracted
                        last_summarized_index = len(messages) - 1

                await self._save_checkpoint(
                    db, run_spec, session, messages, next_turn,
                    session_memory=new_session_memory,
                    last_summarized_message_index=last_summarized_index,
                )
                try:
                    await roll_forward_cross_session_memory(
                        db,
                        self.model_gateway,
                        user_id_hash=session.user_id_hash,
                        agent_id=session.agent_id or run_spec.agent_id,
                        run_id=run_spec.run_id,
                        messages=messages,
                        cfg=ctx_cfg,
                        main_model=model,
                    )
                except Exception:
                    logger.exception("roll_forward_cross_session_memory_skipped")
                profiler.checkpoint("done")
                summary = profiler.finish()
                logger.info("query_profile_turn", extra=summary)
                yield {
                    "type": "done",
                    "output": assistant_safe,
                    "schema_valid": valid,
                    "message_id": message_id,
                    "usage": last_usage,
                }
                if valid is False:
                    logger.info(
                        "schema_validation_failed",
                        extra={
                            "run_id": run_spec.run_id,
                            "output_len": len(assistant_safe),
                        },
                    )
                    yield {
                        "type": "error",
                        "code": "SCHEMA_VALIDATION_FAILED",
                        "message": "输出格式校验失败",
                    }
                return

            # Execute tool calls (partitioned: concurrent safe batches first)
            import asyncio

            from agent_factory.core.tool_partition import partition_tool_calls

            tool_results_for_summary: list[dict[str, Any]] = []
            batches = partition_tool_calls(tool_calls_buffer, self.tool_gateway)

            async def _exec_one(tc: dict[str, Any]) -> dict[str, Any]:
                func = tc.get("function", {})
                tool_id = func.get("name", "")
                if denial_tracker.is_blocked():
                    return {
                        "ok": False,
                        "exc": AgentFactoryException(
                            "DENIAL_LIMIT",
                            "连续多次权限拒绝，已自动阻断后续工具调用",
                            status_code=403,
                        ),
                        "tc": tc,
                    }
                try:
                    params = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    params = {}
                try:
                    result = await self.tool_gateway.validate_and_run_async(
                        db,
                        tool_id=tool_id,
                        params=params,
                        allowed_tools=eff_allowed,
                        retrieval_scopes=run_spec.retrieval_scopes or [],
                        department=session.department,
                        run_spec=run_spec,
                        caller_permissions=caller_permissions,
                        degradation_knobs=degradation_knobs,
                        session_id=session.session_id,
                        model_gateway=self.model_gateway,
                    )
                    return {"ok": True, "result": result, "tc": tc}
                except AgentFactoryException as exc:
                    if exc.code in ("FORBIDDEN", "TOOL_NOT_ALLOWED"):
                        denial_tracker.check_and_record(tool_id, denied=True)
                    return {"ok": False, "exc": exc, "tc": tc}

            async def _emit_result(res: dict[str, Any]) -> AsyncGenerator[dict[str, Any], None]:
                tc = res["tc"]
                tool_id = tc.get("function", {}).get("name", "")
                call_id = tc.get("id", "")
                if res["ok"]:
                    result = res["result"]
                    preview = json.dumps(result, ensure_ascii=False)[:500]
                    yield {
                        "type": "tool_result",
                        "tool_id": tool_id,
                        "call_id": call_id,
                        "preview": preview,
                    }
                    await record_event(
                        db,
                        run_id=run_spec.run_id,
                        session_id=session.session_id,
                        turn_number=next_turn,
                        event_type="tool_result",
                        payload={"tool_id": tool_id, "call_id": call_id, "preview": preview},
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": (
                                (apply_post_sampling_hooks(assistant_text, run_spec) or "")
                                .strip()
                                or None
                            ),
                            "tool_calls": [tc],
                        }
                    )
                    content = await tool_result_payload_for_api(
                        result,
                        ctx_cfg,
                        self.model_gateway,
                        main_model=model,
                    )
                    # Tool Result Budget: persist large results to MinIO
                    if should_persist_tool_result(content, ctx_cfg):
                        try:
                            settings = get_settings()
                            minio = MinioClient(settings)
                            path = await persist_large_tool_result(
                                minio,
                                bucket=settings.MINIO_BUCKET,
                                run_id=run_spec.run_id,
                                turn=turn,
                                tool_call_id=call_id,
                                content=content,
                            )
                            content = make_tool_result_stub(
                                minio_path=path,
                                preview=content[:500],
                            )
                        except Exception:
                            logger.exception("tool_result_persist_failed")

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": content,
                        }
                    )
                    tool_results_for_summary.append({
                        "tool_id": tool_id,
                        "call_id": call_id,
                        "result_preview": preview,
                    })
                else:
                    exc = res["exc"]
                    logger.warning("Tool call failed: %s", exc)
                    err_body = json.dumps(
                        {
                            "ok": False,
                            "code": exc.code,
                            "message": exc.message or "工具执行失败",
                        },
                        ensure_ascii=False,
                    )
                    yield {
                        "type": "tool_result",
                        "tool_id": tool_id,
                        "call_id": call_id,
                        "preview": err_body[:500],
                        "ok": False,
                        "code": exc.code,
                    }
                    await record_event(
                        db,
                        run_id=run_spec.run_id,
                        session_id=session.session_id,
                        turn_number=next_turn,
                        event_type="tool_result",
                        payload={"tool_id": tool_id, "call_id": call_id, "error": exc.code},
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": (
                                (apply_post_sampling_hooks(assistant_text, run_spec) or "")
                                .strip()
                                or None
                            ),
                            "tool_calls": [tc],
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": str(call_id),
                            "content": err_body,
                        }
                    )

                # Intermediate checkpoint after each tool result
                await self._save_checkpoint(
                    db, run_spec, session, messages, next_turn
                )

            for batch in batches:
                if len(batch) > 1:
                    # Concurrent batch: yield running for all, then gather
                    for tc in batch:
                        func = tc.get("function", {})
                        yield {
                            "type": "tool_call",
                            "tool_id": func.get("name", ""),
                            "call_id": tc.get("id", ""),
                            "status": "running",
                        }
                        await record_event(
                            db,
                            run_id=run_spec.run_id,
                            session_id=session.session_id,
                            turn_number=next_turn,
                            event_type="tool_call_start",
                            payload={"tool_id": func.get("name", ""), "call_id": tc.get("id", "")},
                        )
                    batch_results = await asyncio.gather(*[_exec_one(tc) for tc in batch])
                    for res in batch_results:
                        async for evt in _emit_result(res):
                            yield evt
                else:
                    tc = batch[0]
                    func = tc.get("function", {})
                    yield {
                        "type": "tool_call",
                        "tool_id": func.get("name", ""),
                        "call_id": tc.get("id", ""),
                        "status": "running",
                    }
                    await record_event(
                        db,
                        run_id=run_spec.run_id,
                        session_id=session.session_id,
                        turn_number=next_turn,
                        event_type="tool_call_start",
                        payload={"tool_id": func.get("name", ""), "call_id": tc.get("id", "")},
                    )
                    res = await _exec_one(tc)
                    async for evt in _emit_result(res):
                        yield evt

            profiler.checkpoint("tool_execution")
            continue

        # Max turns reached — return partial assistant text if any
        partial_out = ""
        for m in reversed(messages):
            if m.get("role") == "assistant":
                c = m.get("content")
                if isinstance(c, str) and c.strip():
                    partial_out = c.strip()
                    break
        if partial_out:
            yield {
                "type": "done",
                "output": partial_out,
                "usage": last_usage,
                "schema_valid": None,
                "status": "partial",
            }
        yield {
            "type": "error",
            "code": "MAX_TURNS_REACHED",
            "message": "本轮推理步数已达上限，可直接在同一会话续问",
        }

    async def _load_history(
        self, db: AsyncSession, session: ChatSession
    ) -> tuple[list[dict[str, Any]], int | None]:
        """Return (messages, last_summarized_message_index from latest checkpoint)."""
        if not session.run_id:
            return [], None
        q = await db.execute(
            select(Checkpoint)
            .where(Checkpoint.run_id == session.run_id)
            .order_by(Checkpoint.turn_number.desc(), Checkpoint.timestamp.desc())
            .limit(1)
        )
        cp = q.scalar_one_or_none()
        last_index: int | None = None
        if cp:
            last_index = cp.last_summarized_message_index
        if cp and cp.messages:
            msgs = list(cp.messages)
            # Expand any tool result stubs from MinIO
            settings = get_settings()
            minio = None
            for m in msgs:
                if m.get("role") == "tool":
                    c = m.get("content")
                    if isinstance(c, str) and is_tool_result_stub(c):
                        stub = parse_tool_result_stub(c)
                        if stub:
                            try:
                                if minio is None:
                                    minio = MinioClient(settings)
                                full = await load_tool_result_from_persistence(
                                    minio,
                                    bucket=settings.MINIO_BUCKET,
                                    minio_path=stub["minio_path"],
                                )
                                m["content"] = full
                            except Exception:
                                logger.exception("history_stub_expand_failed")
            return msgs, last_index
        return [], last_index

    async def _save_checkpoint(
        self,
        db: AsyncSession,
        run_spec: RunSpec,
        session: ChatSession,
        messages: list[dict[str, Any]],
        turn_number: int,
        session_memory: SessionMemory | None = None,
        last_summarized_message_index: int | None = None,
    ) -> None:
        cp = Checkpoint(
            checkpoint_id=f"cp_{uuid.uuid4().hex[:12]}",
            run_id=run_spec.run_id,
            session_id=session.session_id,
            turn_number=turn_number,
            timestamp=_utc_now(),
            messages=messages,
            token_count=0,
            tool_calls_so_far=None,
            session_memory=session_memory.model_dump() if session_memory else None,
            last_summarized_message_index=last_summarized_message_index,
            created_at=_utc_now(),
        )
        db.add(cp)
        # Update session
        session.turn_count = turn_number
        session.last_activity = _utc_now()
        await db.flush()
