#!/usr/bin/env python3
"""Smoke-test MiniMax OpenAI-compatible streaming (uses Settings / backend .env).

Usage (from repo root or backend/):
  cd backend && uv run python scripts/test_minimax_openai_chat.py

Exit 0 on first streamed token; prints non-sensitive error on failure.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_SRC = _BACKEND / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


async def main() -> int:
    from agent_factory.config.settings import get_settings
    from agent_factory.infra.model_client import ModelClient

    s = get_settings()
    key = (s.MINIMAX_API_KEY or "").strip()
    if not key:
        print("MINIMAX_API_KEY is empty; set it in backend/.env")
        return 2

    # Optional CLI override: python scripts/test_minimax_openai_chat.py https://api.minimaxi.com/v1
    if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
        endpoint = sys.argv[1].rstrip("/")
        if not endpoint.endswith("/v1"):
            endpoint = endpoint + "/v1"
    else:
        # Default matches models.yaml (国内节点；国际密钥请传参 .io URL)
        endpoint = "https://api.minimaxi.com/v1"
    client = ModelClient(endpoint=endpoint, api_key=key, timeout=60.0)
    text_parts: list[str] = []
    try:
        async for chunk in client.chat_completions(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Reply with one word: pong"}],
            max_tokens=32,
            stream=True,
        ):
            for ch in chunk.choices:
                text_parts.append(ch.delta or "")
    except Exception as exc:
        print("FAIL:", type(exc).__name__, str(exc)[:300])
        return 1
    finally:
        await client.close()

    joined = "".join(text_parts).strip()
    print("OK endpoint=", endpoint, "stream_chars=", len(joined))
    print("preview:", repr(joined[:120]))
    return 0 if joined else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
