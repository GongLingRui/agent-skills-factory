"""Session memory: per-turn extraction injected into system prompt (Stage B)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.core.session_memory_schema import SessionMemory, render_for_prompt
from agent_factory.db.models.checkpoint import Checkpoint
from agent_factory.services.conversation_summarize import (
    collect_completion_text,
    format_messages_plain,
)
from agent_factory.services.model_gateway import ModelGateway

logger = logging.getLogger(__name__)

_DEFAULT_TRIGGER_TURNS = 3
_DEFAULT_TRIGGER_TOKENS = 6000


class SessionMemoryExtractor:
    """Extract key facts from recent turns and store in checkpoint."""

    def __init__(
        self,
        model_gateway: ModelGateway,
        *,
        trigger_every_n_turns: int = _DEFAULT_TRIGGER_TURNS,
        trigger_token_threshold: int = _DEFAULT_TRIGGER_TOKENS,
        minimum_tokens_between_update: int = 2048,
    ) -> None:
        self.model_gateway = model_gateway
        self.trigger_every_n_turns = max(1, trigger_every_n_turns)
        self.trigger_token_threshold = max(1024, trigger_token_threshold)
        self.minimum_tokens_between_update = max(512, minimum_tokens_between_update)

    def should_extract(
        self,
        turn_number: int,
        messages: list[dict[str, Any]],
        existing_memory: SessionMemory | None,
        *,
        last_summarized_message_index: int | None = None,
    ) -> bool:
        """Trigger if enough turns elapsed or token estimate exceeds threshold."""
        if turn_number <= 0:
            return False
        if turn_number % self.trigger_every_n_turns == 0:
            return True
        chars = sum(len(str(m.get("content", ""))) for m in messages)
        est_tokens = chars // 4
        if est_tokens >= self.trigger_token_threshold:
            return True
        if existing_memory is None and turn_number >= 2:
            # First extraction after at least 2 turns
            return True
        # Incremental guard: skip if not enough new messages since last extraction
        if last_summarized_message_index is not None:
            new_msgs = messages[last_summarized_message_index + 1 :]
            new_chars = sum(len(str(m.get("content", ""))) for m in new_msgs)
            new_tokens = new_chars // 4
            if new_tokens < self.minimum_tokens_between_update:
                return False
        return False

    async def extract(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        last_summarized_message_index: int | None = None,
    ) -> SessionMemory | None:
        """Forked model call to extract structured session memory."""
        source = messages
        if last_summarized_message_index is not None:
            source = messages[last_summarized_message_index + 1 :]
        if len(source) < 2:
            return None
        tail = source[-8:] if len(source) > 8 else source
        transcript = format_messages_plain(
            [m for m in tail if isinstance(m, dict)],
            max_chars=12_000,
        )
        if not transcript.strip():
            return None
        sys_msg = (
            "你是「会话记忆提取助手」。从以下对话中提取结构化信息，"
            "输出严格 JSON 格式，字段：facts（关键事实列表）、preferences（用户偏好列表）、"
            "decisions（已确认决定列表）、todos（待办事项列表）、"
            "terms（专有名词列表，每项为 {name, definition}）。"
            "不要开场白，只输出 JSON。"
        )
        user_msg = f"待提取对话：\n\n{transcript}"
        try:
            out = await collect_completion_text(
                self.model_gateway,
                model=model,
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=1024,
                temperature=0.15,
                concurrency_class="batch",
                queue_priority=1,
            )
        except Exception:
            logger.exception("session_memory_extraction_failed")
            return None
        out = out.strip()
        if not out:
            return None
        # Try JSON parse
        try:
            # Strip markdown fences if present
            raw = out
            if raw.startswith("```"):
                lines = raw.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw = "\n".join(lines)
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return SessionMemory(
                    facts=_to_str_list(parsed.get("facts")),
                    preferences=_to_str_list(parsed.get("preferences")),
                    decisions=_to_str_list(parsed.get("decisions")),
                    todos=_to_str_list(parsed.get("todos")),
                    terms=_to_term_list(parsed.get("terms")),
                    raw_text="",
                )
        except json.JSONDecodeError:
            logger.warning("session_memory_json_parse_failed_fallback_to_text")
        # Fallback: store raw text
        return SessionMemory(raw_text=out)


async def load_latest_session_memory(
    db: AsyncSession,
    run_id: str,
) -> SessionMemory | None:
    """Load session_memory from the most recent checkpoint for a run."""
    q = await db.execute(
        select(Checkpoint.session_memory)
        .where(Checkpoint.run_id == run_id)
        .order_by(Checkpoint.turn_number.desc())
        .limit(1)
    )
    raw = q.scalar_one_or_none()
    if raw is None:
        return None
    if isinstance(raw, dict):
        # Structured JSONB
        try:
            return SessionMemory(
                facts=_to_str_list(raw.get("facts")),
                preferences=_to_str_list(raw.get("preferences")),
                decisions=_to_str_list(raw.get("decisions")),
                todos=_to_str_list(raw.get("todos")),
                terms=_to_term_list(raw.get("terms")),
                raw_text=str(raw.get("raw_text") or ""),
            )
        except Exception:
            logger.warning("session_memory_structured_parse_failed")
            text = str(raw.get("text") or "").strip()
            return SessionMemory(raw_text=text) if text else None
    if isinstance(raw, str):
        text = raw.strip()
        return SessionMemory(raw_text=text) if text else None
    return None


def inject_session_memory_into_system(
    system_content: str,
    memory: SessionMemory | None,
) -> str:
    """Append session memory section to system prompt if present."""
    if not memory or memory.is_empty():
        return system_content
    rendered = render_for_prompt(memory)
    if not rendered:
        return system_content
    section = f"\n\n## 当前会话记忆（自动提取）\n{rendered}"
    if section in system_content:
        return system_content
    return system_content + section


def _to_str_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(v) for v in val if v is not None]
    return []


def _to_term_list(val: Any) -> list[dict[str, str]]:
    if not isinstance(val, list):
        return []
    out: list[dict[str, str]] = []
    for item in val:
        if isinstance(item, dict):
            name = str(item.get("name") or "")
            definition = str(item.get("definition") or "")
            if name:
                out.append({"name": name, "definition": definition})
    return out
