"""Model gateway: routing, fallback, basic rate limiting (docs/10)."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from agent_factory.config import Settings
from agent_factory.infra.model_client import (
    ChatChoice,
    ChatChunk,
    ModelClient,
    ModelClientError,
    PromptTooLongError,
    StreamingInterruptedError,
)
from agent_factory.infra.model_queue import (
    ModelQueuePolicyError,
    acquire_model_queue_slot,
)
from agent_factory.infra.model_runtime_signals import (
    record_model_attempt,
    record_model_failure,
    record_model_latency_sample,
    record_model_success_ms,
)
from agent_factory.infra.redis import get_redis

logger = logging.getLogger(__name__)


async def _dev_mock_chat_stream(
    messages: list[dict[str, Any]],
) -> AsyncGenerator[ChatChunk, None]:
    """Deterministic assistant text for local dev (no HTTP to model vendors)."""
    last = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content", "")
            last = c if isinstance(c, str) else str(c)
            break
    snippet = last[:500]
    body = (
        "[本地开发 MOCK，未调用真实模型]\n\n"
        f"用户：{snippet or '（空）'}\n\n"
        "关闭方式：backend .env 中设 MODEL_DEV_MOCK=false，并配置 "
        "models.yaml 中可用的 endpoint 与 API 密钥。"
    )
    yield ChatChunk(
        choices=[ChatChoice(delta=body, finish_reason=None)],
        model="dev-mock",
        usage=None,
    )
    n = max(1, len(body) // 4)
    yield ChatChunk(
        choices=[ChatChoice(delta="", finish_reason="stop")],
        model="dev-mock",
        usage={"prompt_tokens": 10, "completion_tokens": n, "total_tokens": 10 + n},
    )


@dataclass
class ModelConfig:
    name: str
    endpoint: str
    api_key: str
    max_tokens: int
    rpm: int
    tpm: int
    health_endpoint: str | None
    fallback_order: list[str]
    provider: str
    api_model: str | None


class ModelGateway:
    """Load models.yaml, route requests, handle fallback chain."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._models: dict[str, ModelConfig] = {}
        self._clients: dict[str, ModelClient] = {}
        self._defaults: dict[str, Any] = {}
        self._aliases: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        path = Path(self.settings.MODELS_CONFIG_PATH)
        if not path.is_file():
            logger.warning("models.yaml not found at %s", path)
            return
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            logger.exception("Failed to load models.yaml")
            return

        models = data.get("models") or {}
        aliases_raw = data.get("model_aliases") or {}
        self._aliases = {}
        if isinstance(aliases_raw, dict):
            for k, v in aliases_raw.items():
                if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                    self._aliases[k.strip()] = v.strip()
        for name, cfg in models.items():
            self._models[name] = ModelConfig(
                name=name,
                endpoint=cfg.get("endpoint", ""),
                api_key=self._resolve_secret(cfg.get("api_key", "")),
                max_tokens=cfg.get("max_tokens", 8192),
                rpm=cfg.get("rpm", 60),
                tpm=cfg.get("tpm", 100000),
                health_endpoint=cfg.get("health_endpoint"),
                fallback_order=cfg.get("fallback_order", []),
                provider=str(cfg.get("provider", "openai_compatible")),
                api_model=(
                    str(cfg["api_model"]).strip()
                    if isinstance(cfg.get("api_model"), str)
                    and str(cfg["api_model"]).strip()
                    else None
                ),
            )
        self._defaults = data.get("defaults", {})

    def default_chat_model(self) -> str:
        """Logical name from ``defaults.model`` in ``models.yaml``."""
        return str(self._defaults.get("model") or "MiniMax-M2.7")

    def expand_alias(self, raw: str) -> str:
        """Map user/widget shortcut to logical ``models`` key (if registered)."""
        s = raw.strip()
        if not s:
            return self.default_chat_model()
        return self._aliases.get(s, s)

    def is_logical_model_configured(self, logical: str) -> bool:
        """True iff ``logical`` is a key in ``models`` (after alias expansion)."""
        key = self.expand_alias(logical)
        return key in self._models

    def list_model_catalog(self) -> list[dict[str, Any]]:
        """Widget / portal: selectable OpenAI-compatible routes (docs/10)."""
        out: list[dict[str, Any]] = []
        for name, cfg in sorted(self._models.items(), key=lambda x: x[0].lower()):
            host = ""
            if cfg.endpoint:
                try:
                    host = urlparse(cfg.endpoint).netloc or cfg.endpoint
                except Exception:
                    host = cfg.endpoint[:48]
            out.append(
                {
                    "id": name,
                    "provider": cfg.provider,
                    "endpoint_host": host,
                    "api_model": cfg.api_model or name,
                    "max_tokens": cfg.max_tokens,
                    "rpm": cfg.rpm,
                }
            )
        return out

    def list_model_aliases(self) -> dict[str, str]:
        """Shortcut → logical id (same file as Claude Code-style /model presets)."""
        return dict(self._aliases)

    def rpm_for(self, logical_model: str) -> int:
        """Configured RPM for the resolved model (defaults to 60)."""
        resolved = self.resolve_model(logical_model)
        cfg = self._models.get(resolved)
        if cfg is None:
            return 60
        return int(cfg.rpm)

    def _resolve_secret(self, value: str) -> str:
        if value.startswith("${") and value.endswith("}"):
            inner = value[2:-1]
            if ":-" in inner:
                key, default = inner.split(":-", 1)
                return getattr(self.settings, key, default) or default
            return getattr(self.settings, inner, "") or ""
        return value

    def _client(self, model_name: str) -> ModelClient:
        if model_name not in self._clients:
            cfg = self._models[model_name]
            self._clients[model_name] = ModelClient(
                endpoint=cfg.endpoint,
                api_key=cfg.api_key,
                timeout=cfg.max_tokens / 100,  # rough heuristic
            )
        return self._clients[model_name]

    def _chat_attempt_chain(self, resolved: str) -> list[str]:
        """Models to try in order: primary + yaml fallbacks + defaults fallback.

        Local qwen endpoints often point at unused ports; appending the default
        cloud model avoids stopping after the first failed fallback (see
        ``except`` handling in ``_chat_stream``).
        """
        cfg = self._models.get(resolved)
        if cfg is None:
            return []
        chain: list[str] = []
        for name in (resolved, *cfg.fallback_order):
            if name not in chain:
                chain.append(name)
        ultimate = str(
            self._defaults.get("fallback_model") or self.default_chat_model()
        )
        if ultimate and ultimate not in chain:
            chain.append(ultimate)
        return chain

    def resolve_model(self, run_spec_model: str) -> str:
        """Return the best available model key, walking fallback if unknown."""
        visited: set[str] = set()
        current = self.expand_alias(run_spec_model)
        while current:
            if current in self._models:
                return current
            visited.add(current)
            cfg = self._models.get(current)
            if not cfg:
                break
            for fb in cfg.fallback_order:
                if fb not in visited:
                    current = fb
                    break
            else:
                break
        # ultimate fallback from defaults (avoid implicit localhost qwen)
        return self._defaults.get("fallback_model", "MiniMax-M2.7")

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        concurrency_class: str = "interactive",
        queue_priority: int = 5,
    ) -> AsyncGenerator[ChatChunk, None]:
        """Stream chat completions through the resolved model (queued)."""
        await record_model_attempt()
        t0 = time.perf_counter()
        redis = get_redis()
        success = False
        try:
            async with acquire_model_queue_slot(
                redis,
                self.settings,
                concurrency_class,
                queue_priority=queue_priority,
            ):
                async for chunk in self._chat_stream(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tools=tools,
                ):
                    yield chunk
            success = True
        except ModelQueuePolicyError:
            raise
        except Exception:
            await record_model_failure()
            raise
        finally:
            if success:
                ms = (time.perf_counter() - t0) * 1000.0
                await record_model_success_ms(ms)
                await record_model_latency_sample(ms)

    async def _chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int | None,
        temperature: float | None,
        tools: list[dict[str, Any]] | None,
    ) -> AsyncGenerator[ChatChunk, None]:
        """Inner stream after queue slot acquired."""
        resolved = self.resolve_model(model)
        cfg = self._models.get(resolved)
        if cfg is None:
            raise ModelClientError(f"Model {resolved} not configured")

        if self.settings.MODEL_DEV_MOCK and self.settings.APP_ENV == "development":
            async for chunk in _dev_mock_chat_stream(messages):
                yield chunk
            return

        attempt_chain = self._chat_attempt_chain(resolved)
        if not attempt_chain:
            raise ModelClientError(f"Model {resolved} not configured")

        last_error: ModelClientError | None = None
        primary = attempt_chain[0]

        for attempt_model in attempt_chain:
            m_cfg = self._models.get(attempt_model)
            if m_cfg is None:
                continue
            if attempt_model != primary:
                logger.warning("Fallback %s -> %s", primary, attempt_model)
            client = self._client(attempt_model)
            api_model_id = m_cfg.api_model or attempt_model
            try:
                async for chunk in client.chat_completions(
                    model=api_model_id,
                    messages=messages,
                    max_tokens=max_tokens or m_cfg.max_tokens,
                    temperature=temperature,
                    tools=tools,
                    stream=True,
                ):
                    yield chunk
                return
            except PromptTooLongError:
                raise
            except StreamingInterruptedError as exc:
                logger.warning(
                    "Model %s stream interrupted (%s), falling back to non-stream",
                    attempt_model,
                    exc,
                )
                try:
                    # Non-streaming fallback: yield the single complete chunk
                    fallback_yielded = False
                    async for chunk in client.chat_completions(
                        model=api_model_id,
                        messages=messages,
                        max_tokens=max_tokens or m_cfg.max_tokens,
                        temperature=temperature,
                        tools=tools,
                        stream=False,
                    ):
                        yield chunk
                        fallback_yielded = True
                    if fallback_yielded:
                        return
                    # If generator was empty, treat as failure and try next model
                    raise ModelClientError("Empty non-streaming fallback response")
                except ModelClientError as fb_exc:
                    last_error = fb_exc
                    logger.warning(
                        "Model %s non-stream fallback also failed (%s), trying next in chain",
                        attempt_model,
                        fb_exc,
                    )
                    continue
            except ModelClientError as exc:
                last_error = exc
                logger.warning(
                    "Model %s failed (%s), trying next in chain",
                    attempt_model,
                    exc,
                )
                continue

        if last_error is not None:
            raise last_error
        raise ModelClientError(f"No model attempted for {resolved}")

    async def close(self) -> None:
        for client in self._clients.values():
            await client.close()
