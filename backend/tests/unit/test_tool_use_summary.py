"""Tests for tool_use_summary generation."""

from __future__ import annotations

import pytest

from agent_factory.services.tool_use_summary import generate_tool_use_summary


class FakeModelGateway:
    def __init__(self, return_text: str = "工具摘要") -> None:
        self.return_text = return_text

    async def chat(self, **kwargs):
        from agent_factory.infra.model_client import ChatChunk, ChatChoice

        yield ChatChunk(
            choices=[ChatChoice(delta=self.return_text, finish_reason="stop")],
            model="fake",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )


@pytest.mark.anyio
async def test_generate_tool_use_summary_returns_string():
    gw = FakeModelGateway(return_text="本次调用了知识检索和文档提取工具，获取了相关政策文件。")
    results = [
        {"tool_id": "kb.search", "call_id": "c1", "result_preview": "找到3条政策"},
        {"tool_id": "doc.extract", "call_id": "c2", "result_preview": "提取了5页内容"},
    ]
    out = await generate_tool_use_summary(gw, model="fake", tool_results=results, max_tokens=256)
    assert isinstance(out, str)
    assert len(out) > 0


@pytest.mark.anyio
async def test_generate_tool_use_summary_empty_input():
    gw = FakeModelGateway()
    out = await generate_tool_use_summary(gw, model="fake", tool_results=[], max_tokens=256)
    assert out == ""


@pytest.mark.anyio
async def test_generate_tool_use_summary_exception_fallback():
    class BadGateway:
        async def chat(self, **kwargs):
            raise RuntimeError("boom")

    results = [
        {"tool_id": "kb.search", "call_id": "c1", "result_preview": "找到3条政策"},
    ]
    out = await generate_tool_use_summary(BadGateway(), model="fake", tool_results=results)
    assert out == ""
