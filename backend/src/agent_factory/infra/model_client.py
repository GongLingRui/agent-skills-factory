"""OpenAI-compatible async HTTP client for model inference."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ChatChoice:
    delta: str = ""
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


@dataclass
class ChatChunk:
    choices: list[ChatChoice]
    model: str = ""
    usage: dict[str, int] | None = None


class ModelClientError(Exception):
    pass


class PromptTooLongError(ModelClientError):
    """Raised when the model rejects the prompt due to context length."""
    pass


class StreamingInterruptedError(ModelClientError):
    """Raised when the stream drops mid-response (network, proxy, timeout).

    Distinguished from terminal HTTP errors so the gateway can fall back to
    a non-streaming retry.
    """
    pass


def _is_prompt_too_long(detail: str) -> bool:
    """Detect context-length exceeded signals from common providers."""
    low = detail.lower()
    markers = (
        "prompt_too_long",
        "context_length_exceeded",
        "maximum context length",
        "too many tokens",
        "token limit",
        "prompt is too long",
        "input length",
        "contextwindow",
        "max_position_embeddings",
    )
    return any(m in low for m in markers)


def _delta_text_from_openai_delta(delta_raw: Any) -> str:
    """Collect streamed assistant text from OpenAI-shaped ``delta`` objects.

    MiniMax (and others) may send chain-of-thought in ``reasoning_content`` or
    ``reasoning_details`` while ``content`` is empty for some chunks; merging
    avoids empty second-round assistant text after tool results.
    """
    if not isinstance(delta_raw, dict):
        return ""
    parts: list[str] = []
    for key in ("content", "reasoning_content"):
        val = delta_raw.get(key)
        if isinstance(val, str) and val:
            parts.append(val)
    rd = delta_raw.get("reasoning_details")
    if isinstance(rd, str) and rd.strip():
        parts.append(rd)
    elif isinstance(rd, list):
        for item in rd:
            if isinstance(item, dict):
                t = item.get("text")
                if isinstance(t, str) and t:
                    parts.append(t)
    return "".join(parts)


class ModelClient:
    """Thin async client wrapping OpenAI-compatible chat completions."""

    def __init__(self, endpoint: str, api_key: str, timeout: float = 90.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        # follow_redirects=False: avoid open-redirect / SSRF chains (信息安全 §3.2-15).
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=timeout, write=60.0, pool=30.0),
            follow_redirects=False,
            http2=False,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=20),
        )

    async def chat_completions(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[ChatChunk, None]:
        url = f"{self.endpoint}/chat/completions"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if stream:
            headers["Accept"] = "text/event-stream"

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = tools

        try:
            if stream:
                async with self._client.stream(
                    "POST", url, headers=headers, json=payload
                ) as response:
                    if response.status_code >= 400:
                        text = await response.aread()
                        detail = text.decode(errors="replace").strip()[:500]
                        if not detail:
                            detail = "(empty response body; check endpoint, API key, proxy)"
                        if response.status_code == 400 and _is_prompt_too_long(detail):
                            raise PromptTooLongError(f"HTTP {response.status_code}: {detail}")
                        raise ModelClientError(f"HTTP {response.status_code}: {detail}")

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                obj = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            yield self._parse_chunk(obj)
            else:
                response = await self._client.post(
                    url, headers=headers, json=payload
                )
                if response.status_code >= 400:
                    detail = response.text.strip()[:500]
                    if not detail:
                        detail = "(empty response body; check endpoint, API key, proxy)"
                    if response.status_code == 400 and _is_prompt_too_long(detail):
                        raise PromptTooLongError(f"HTTP {response.status_code}: {detail}")
                    raise ModelClientError(f"HTTP {response.status_code}: {detail}")
                obj = response.json()
                yield self._parse_non_streaming(obj)
        except httpx.HTTPError as exc:
            # Distinguish mid-stream drops from terminal HTTP errors so the
            # gateway can retry non-streaming.
            if stream:
                raise StreamingInterruptedError(f"Stream dropped: {exc}") from exc
            raise ModelClientError(f"HTTP error: {exc}") from exc

    def _parse_non_streaming(self, obj: dict[str, Any]) -> ChatChunk:
        """Wrap a complete non-streaming response as a single ChatChunk."""
        choices_raw = obj.get("choices") or []
        choices: list[ChatChoice] = []
        for c in choices_raw:
            msg = c.get("message") or {}
            tool_calls = msg.get("tool_calls")
            choices.append(
                ChatChoice(
                    delta=_delta_text_from_openai_delta(msg),
                    finish_reason=c.get("finish_reason"),
                    tool_calls=tool_calls,
                )
            )
        return ChatChunk(
            choices=choices,
            model=obj.get("model", ""),
            usage=obj.get("usage"),
        )

    def _parse_chunk(self, obj: dict[str, Any]) -> ChatChunk:
        choices_raw = obj.get("choices") or []
        choices: list[ChatChoice] = []
        for c in choices_raw:
            delta_raw = c.get("delta") or {}
            tool_calls = delta_raw.get("tool_calls")
            choices.append(
                ChatChoice(
                    delta=_delta_text_from_openai_delta(delta_raw),
                    finish_reason=c.get("finish_reason"),
                    tool_calls=tool_calls,
                )
            )
        return ChatChunk(
            choices=choices,
            model=obj.get("model", ""),
            usage=obj.get("usage"),
        )

    async def close(self) -> None:
        await self._client.aclose()
