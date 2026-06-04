"""Feishu/Lark Open API client (tenant token + IM send/reply)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Literal

import httpx

from agent_factory.config import Settings, get_settings

logger = logging.getLogger(__name__)

_TOKEN_SKEW_SECONDS = 120
FeishuReplyFormat = Literal["text", "markdown"]


def build_interactive_markdown_content(text: str) -> str:
    """Wrap assistant markdown in Feishu card schema 2.0 for rich rendering."""
    body = (text or "").strip() or "（无回复内容）"
    card = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "body": {
            "direction": "vertical",
            "elements": [{"tag": "markdown", "content": body}],
        },
    }
    return json.dumps(card, ensure_ascii=False)


class FeishuClient:
    """Minimal async Feishu REST client with in-memory tenant token cache."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def api_base(self) -> str:
        return self.settings.feishu_api_base

    async def get_tenant_access_token(self) -> str:
        async with self._lock:
            now = time.time()
            if self._token and now < self._token_expires_at - _TOKEN_SKEW_SECONDS:
                return self._token
            app_id = self.settings.FEISHU_APP_ID.strip()
            app_secret = self.settings.FEISHU_APP_SECRET.strip()
            if not app_id or not app_secret:
                raise RuntimeError("FEISHU_APP_ID and FEISHU_APP_SECRET are required")
            url = f"{self.api_base}/open-apis/auth/v3/tenant_access_token/internal"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    json={"app_id": app_id, "app_secret": app_secret},
                )
                resp.raise_for_status()
                data = resp.json()
            if int(data.get("code", -1)) != 0:
                raise RuntimeError(
                    f"Feishu token error: {data.get('msg') or data.get('code')}"
                )
            token = str(data.get("tenant_access_token") or "")
            if not token:
                raise RuntimeError("Feishu token response missing tenant_access_token")
            expire = int(data.get("expire") or 7200)
            self._token = token
            self._token_expires_at = now + max(60, expire)
            return token

    async def _auth_headers(self) -> dict[str, str]:
        token = await self.get_tenant_access_token()
        return {"Authorization": f"Bearer {token}"}

    async def _post_message(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        params: dict[str, str] | None = None,
        log_label: str,
    ) -> dict[str, Any]:
        headers = await self._auth_headers()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers=headers,
                params=params,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        if int(data.get("code", -1)) != 0:
            raise RuntimeError(
                f"Feishu {log_label} failed: {data.get('msg') or data}"
            )
        return data

    async def send_message(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        msg_type: str,
        content: str,
    ) -> dict[str, Any]:
        url = f"{self.api_base}/open-apis/im/v1/messages"
        payload = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content,
        }
        data = await self._post_message(
            url=url,
            payload=payload,
            params={"receive_id_type": receive_id_type},
            log_label="send",
        )
        logger.info(
            "feishu_send_sent receive_id=%s msg_type=%s chars=%d",
            receive_id,
            msg_type,
            len(content),
        )
        return data

    async def reply_message(
        self,
        *,
        message_id: str,
        msg_type: str,
        content: str,
    ) -> dict[str, Any]:
        url = f"{self.api_base}/open-apis/im/v1/messages/{message_id}/reply"
        payload = {"msg_type": msg_type, "content": content}
        data = await self._post_message(
            url=url,
            payload=payload,
            log_label="reply",
        )
        logger.info(
            "feishu_reply_sent message_id=%s msg_type=%s chars=%d",
            message_id,
            msg_type,
            len(content),
        )
        return data

    async def send_text(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        text: str,
    ) -> dict[str, Any]:
        content = json.dumps({"text": text}, ensure_ascii=False)
        return await self.send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="text",
            content=content,
        )

    async def send_markdown(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        text: str,
    ) -> dict[str, Any]:
        content = build_interactive_markdown_content(text)
        return await self.send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="interactive",
            content=content,
        )

    async def reply_text(self, *, message_id: str, text: str) -> dict[str, Any]:
        content = json.dumps({"text": text}, ensure_ascii=False)
        return await self.reply_message(
            message_id=message_id,
            msg_type="text",
            content=content,
        )

    async def reply_markdown(self, *, message_id: str, text: str) -> dict[str, Any]:
        content = build_interactive_markdown_content(text)
        return await self.reply_message(
            message_id=message_id,
            msg_type="interactive",
            content=content,
        )

    async def send_to_chat(
        self,
        *,
        chat_id: str,
        text: str,
        reply_message_id: str | None = None,
        reply_format: FeishuReplyFormat = "markdown",
    ) -> None:
        use_markdown = reply_format == "markdown"
        if reply_message_id:
            try:
                if use_markdown:
                    await self.reply_markdown(
                        message_id=reply_message_id,
                        text=text,
                    )
                else:
                    await self.reply_text(message_id=reply_message_id, text=text)
                return
            except Exception:
                logger.exception("feishu_reply_failed_fallback_to_create")
        try:
            if use_markdown:
                await self.send_markdown(
                    receive_id=chat_id,
                    receive_id_type="chat_id",
                    text=text,
                )
            else:
                await self.send_text(
                    receive_id=chat_id,
                    receive_id_type="chat_id",
                    text=text,
                )
        except Exception:
            if use_markdown:
                logger.exception("feishu_markdown_send_failed_fallback_to_text")
                await self.send_to_chat(
                    chat_id=chat_id,
                    text=text,
                    reply_message_id=None,
                    reply_format="text",
                )
                return
            raise


def split_feishu_text(text: str, max_chars: int) -> list[str]:
    """Split long assistant output into Feishu-safe chunks."""
    body = (text or "").strip()
    if not body:
        return ["（无回复内容）"]
    if len(body) <= max_chars:
        return [body]
    chunks: list[str] = []
    start = 0
    while start < len(body):
        end = min(len(body), start + max_chars)
        if end < len(body):
            split_at = body.rfind("\n", start, end)
            if split_at <= start:
                split_at = end
            else:
                end = split_at
        chunk = body[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks or ["（无回复内容）"]
