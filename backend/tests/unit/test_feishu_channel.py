"""Unit tests for Feishu channel helpers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_factory.services.feishu_client import (
    build_interactive_markdown_content,
    split_feishu_text,
)
from agent_factory.services.feishu_events import (
    parse_im_message_event,
    url_verification_challenge,
)
from agent_factory.services.feishu_transport import _normalize_feishu_transport
from agent_factory.services.feishu_service import (
    FeishuChannelService,
    _AGENTS_TO_FEISHU_DOC,
    feishu_max_turns_for_runtime,
    format_feishu_run_reply,
)


def test_normalize_feishu_transport_aliases():
    assert _normalize_feishu_transport("websocket") == "ws"
    assert _normalize_feishu_transport("ws") == "ws"
    assert _normalize_feishu_transport("webhook") == "webhook"


def test_url_verification_challenge():
    payload = {"type": "url_verification", "challenge": "abc123"}
    assert url_verification_challenge(payload) == "abc123"


def test_parse_im_message_event_text():
    event = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_user"}},
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_chat",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": "帮我写工作总结"}),
            },
        },
    }
    msg = parse_im_message_event(event)
    assert msg is not None
    assert msg.text == "帮我写工作总结"
    assert msg.sender_open_id == "ou_user"


def test_parse_im_message_event_group_mention():
    event = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_user"}},
            "message": {
                "message_id": "om_2",
                "chat_id": "oc_group",
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": "@_user_1 审查合同"}),
                "mentions": [
                    {
                        "key": "@_user_1",
                        "id": {"open_id": "ou_bot"},
                        "name": "AgentBot",
                    }
                ],
            },
        },
    }
    msg = parse_im_message_event(event, bot_open_id="ou_bot")
    assert msg is not None
    assert msg.mentioned_bot is True
    assert msg.text == "审查合同"


def test_split_feishu_text_chunks():
    body = "a" * 5000
    chunks = split_feishu_text(body, 2000)
    assert len(chunks) >= 3
    assert "".join(chunks).replace("\n", "") == body


def test_build_interactive_markdown_content():
    raw = build_interactive_markdown_content("## 标题\n\n**加粗**")
    data = json.loads(raw)
    assert data["schema"] == "2.0"
    assert data["body"]["elements"][0]["tag"] == "markdown"
    assert "## 标题" in data["body"]["elements"][0]["content"]
    assert "**加粗**" in data["body"]["elements"][0]["content"]


def test_agents_to_feishu_doc_intent_regex():
    assert _AGENTS_TO_FEISHU_DOC.search("把所有的可用agents写入到飞书文档中")
    assert _AGENTS_TO_FEISHU_DOC.search("导出 agents 到飞书文档")
    assert _AGENTS_TO_FEISHU_DOC.search("飞书文档里写入全部 agent 列表") is not None


def test_feishu_max_turns_zero_uses_generous_cap(monkeypatch):
    monkeypatch.setenv("FEISHU_MAX_TURNS", "0")
    from agent_factory.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    assert feishu_max_turns_for_runtime(s, {"max_turns": 6}) == 64


def test_format_feishu_run_reply_max_turns_friendly():
    out = format_feishu_run_reply(
        "",
        [{"code": "MAX_TURNS_REACHED", "message": "old"}],
    )
    assert "开新会话" not in out
    assert "继续" in out
    partial = format_feishu_run_reply(
        "已完成一半",
        [{"code": "MAX_TURNS_REACHED"}],
    )
    assert "已完成一半" in partial
    assert "继续" in partial


@pytest.mark.asyncio
async def test_feishu_should_accept_group_without_mention(monkeypatch):
    monkeypatch.setenv("FEISHU_GROUP_REQUIRE_MENTION", "true")
    from agent_factory.config import get_settings

    get_settings.cache_clear()
    svc = FeishuChannelService()
    from agent_factory.services.feishu_events import FeishuInboundMessage

    msg = FeishuInboundMessage(
        message_id="m1",
        chat_id="oc_g",
        chat_type="group",
        sender_open_id="ou_u",
        text="hello",
        mentioned_bot=False,
        raw={},
    )
    assert svc.should_accept(msg) is False
    msg2 = FeishuInboundMessage(
        message_id="m2",
        chat_id="oc_g",
        chat_type="group",
        sender_open_id="ou_u",
        text="hello",
        mentioned_bot=True,
        raw={},
    )
    assert svc.should_accept(msg2) is True


@pytest.mark.asyncio
async def test_resolve_agent_id_keyword(monkeypatch):
    monkeypatch.setenv("FEISHU_ROUTER_USE_LLM", "false")
    monkeypatch.setenv(
        "FEISHU_CANDIDATE_AGENT_IDS",
        "work-summary-agent,contract-to-plan-agent",
    )
    from agent_factory.config import get_settings

    get_settings.cache_clear()

    ag1 = MagicMock()
    ag1.id = "work-summary-agent"
    ag1.name = "工作总结"
    ag1.instruction = "撰写工作总结"
    ag1.owner = "hr"
    ag1.lifecycle_state = "active"

    ag2 = MagicMock()
    ag2.id = "contract-to-plan-agent"
    ag2.name = "合同转方案"
    ag2.instruction = "合同"
    ag2.owner = "legal"
    ag2.lifecycle_state = "active"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [ag1, ag2]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    svc = FeishuChannelService()
    aid, meta = await svc.resolve_agent_id(
        db,
        user_message="请帮我写一份年终工作总结",
        current_agent_id=None,
    )
    assert aid == "work-summary-agent"
    assert meta is not None
