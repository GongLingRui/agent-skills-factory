"""Tests for summarize-first message preparation."""

import pytest

from dataclasses import replace

from agent_factory.core.context_memory import ContextMemorySettings
from agent_factory.infra.model_client import ChatChoice, ChatChunk
from agent_factory.services.conversation_memory import prepare_messages_for_chat_api


class _FakeGW:
    def __init__(self, body: str = "短摘要") -> None:
        self._body = body

    async def chat(self, **kwargs: object) -> object:
        yield ChatChunk(choices=[ChatChoice(delta=self._body, finish_reason=None)])
        yield ChatChunk(
            choices=[ChatChoice(delta="", finish_reason="stop")],
            usage={"total_tokens": 50},
        )


@pytest.mark.asyncio
async def test_prepare_summarize_inserts_memory_bubble() -> None:
    base = ContextMemorySettings.from_runtime({})
    cfg = replace(
        base,
        history_budget_chars=200,
        keep_recent_user_turns=1,
        min_user_turns=1,
        compression="summarize",
    )
    msgs = [
        {"role": "user", "content": "A" * 120},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "B" * 120},
    ]
    out = await prepare_messages_for_chat_api(
        msgs,
        cfg,
        _FakeGW("记忆要点"),
        main_model="MiniMax-M2.7",
    )
    assert len(out) == 4
    assert out[0]["role"] == "system"
    assert "会话摘要边界开始" in out[0]["content"]
    assert "模型摘要" in out[1]["content"]
    assert "记忆要点" in out[1]["content"]
    assert out[2]["role"] == "system"
    assert "会话摘要边界结束" in out[2]["content"]
    assert out[3]["content"] == "B" * 120
