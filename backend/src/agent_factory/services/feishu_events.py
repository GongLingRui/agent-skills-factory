"""Parse and normalize Feishu im.message.receive_v1 events."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeishuInboundMessage:
    message_id: str
    chat_id: str
    chat_type: str
    sender_open_id: str
    text: str
    mentioned_bot: bool
    raw: dict[str, Any]


def _parse_content_text(message_type: str, content_raw: str) -> str:
    if not content_raw:
        return ""
    try:
        obj = json.loads(content_raw)
    except json.JSONDecodeError:
        return content_raw.strip()
    if not isinstance(obj, dict):
        return str(obj).strip()
    if message_type == "text":
        return str(obj.get("text") or "").strip()
    if message_type == "post":
        return _flatten_post_content(obj).strip()
    return str(obj.get("text") or obj).strip()


def _flatten_post_content(obj: dict[str, Any]) -> str:
    parts: list[str] = []
    content = obj.get("content")
    if not isinstance(content, list):
        return str(obj.get("text") or "")
    for block in content:
        if not isinstance(block, list):
            continue
        for item in block:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag") or "")
            if tag == "text":
                parts.append(str(item.get("text") or ""))
            elif tag == "a":
                parts.append(str(item.get("text") or item.get("href") or ""))
    return "".join(parts)


def _bot_mentioned(
    mentions: list[Any] | None,
    *,
    bot_open_id: str | None,
) -> bool:
    if not mentions:
        return False
    bot_id = (bot_open_id or "").strip()
    for m in mentions:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if isinstance(mid, dict):
            oid = str(mid.get("open_id") or "")
            if bot_id and oid == bot_id:
                return True
        name = str(m.get("name") or "")
        if name and ("机器人" in name or "bot" in name.lower()):
            return True
    return False


def strip_bot_mention(text: str) -> str:
    cleaned = re.sub(r"@_user_\d+\s*", "", text)
    cleaned = re.sub(r"@_all\s*", "", cleaned)
    return cleaned.strip()


def parse_im_message_event(
    event: dict[str, Any],
    *,
    bot_open_id: str | None = None,
) -> FeishuInboundMessage | None:
    """Parse Feishu v1/v2 envelope into a normalized inbound message."""
    header = event.get("header")
    if isinstance(header, dict):
        event_type = str(header.get("event_type") or "")
        body = event.get("event")
    else:
        event_type = str(event.get("type") or event.get("event_type") or "")
        body = event.get("event") if isinstance(event.get("event"), dict) else event

    if event_type and event_type not in {
        "im.message.receive_v1",
        "im.message.message_receive_v1",
    }:
        return None
    if not isinstance(body, dict):
        return None

    message = body.get("message")
    sender = body.get("sender")
    if not isinstance(message, dict):
        return None
    message_id = str(message.get("message_id") or "").strip()
    chat_id = str(message.get("chat_id") or "").strip()
    chat_type = str(message.get("chat_type") or "p2p").strip().lower()
    if not message_id or not chat_id:
        return None

    sender_open_id = ""
    if isinstance(sender, dict):
        sid = sender.get("sender_id")
        if isinstance(sid, dict):
            sender_open_id = str(sid.get("open_id") or "").strip()
    if not sender_open_id:
        sender_open_id = str(body.get("open_id") or "unknown").strip()

    message_type = str(message.get("message_type") or "text")
    content_raw = str(message.get("content") or "")
    text = _parse_content_text(message_type, content_raw)
    if not text:
        return None

    mentions = message.get("mentions")
    mention_list = mentions if isinstance(mentions, list) else None
    mentioned = _bot_mentioned(mention_list, bot_open_id=bot_open_id)
    if mention_list:
        text = strip_bot_mention(text)

    return FeishuInboundMessage(
        message_id=message_id,
        chat_id=chat_id,
        chat_type=chat_type,
        sender_open_id=sender_open_id,
        text=text.strip(),
        mentioned_bot=mentioned,
        raw=event,
    )


def is_url_verification(payload: dict[str, Any]) -> bool:
    return str(payload.get("type") or "").strip() == "url_verification"


def url_verification_challenge(payload: dict[str, Any]) -> str | None:
    if not is_url_verification(payload):
        return None
    ch = payload.get("challenge")
    return str(ch) if ch is not None else None
