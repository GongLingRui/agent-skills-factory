"""Emergency shrink keeps assistant context when user says 继续."""

import pytest

from dataclasses import replace

from agent_factory.core.context_memory import ContextMemorySettings
from agent_factory.infra.model_client import ChatChoice, ChatChunk
from agent_factory.services.conversation_memory import prepare_messages_for_chat_api


class _FakeGW:
    async def chat(self, **kwargs: object) -> object:
        yield ChatChunk(choices=[ChatChoice(delta="摘要", finish_reason=None)])
        yield ChatChunk(
            choices=[ChatChoice(delta="", finish_reason="stop")],
            usage={"total_tokens": 50},
        )


@pytest.mark.asyncio
async def test_prepare_keeps_assistant_when_continue_over_budget() -> None:
    base = ContextMemorySettings.from_runtime({})
    cfg = replace(
        base,
        history_budget_chars=500,
        keep_recent_user_turns=4,
        min_user_turns=1,
        compression="summarize",
    )
    huge_html = "H" * 800
    msgs = [
        {"role": "user", "content": "生成 HTML"},
        {"role": "assistant", "content": f"HTML 第 1 段\n```html\n{huge_html}\n```"},
        {"role": "user", "content": "继续"},
    ]
    out = await prepare_messages_for_chat_api(
        msgs,
        cfg,
        _FakeGW(),
        main_model="MiniMax-M2.7",
    )
    roles = [m["role"] for m in out]
    assert roles.count("user") >= 1
    joined = "\n".join(str(m.get("content", "")) for m in out)
    assert "继续" in joined or "第 1 段" in joined or "HTML" in joined
