"""Shared streaming text aggregation for offline eval (scripts + Registry gate)."""

from __future__ import annotations

from agent_factory.services.model_gateway import ModelGateway


async def collect_chat_text_stream(
    gateway: ModelGateway,
    *,
    model: str,
    user_message: str,
) -> str:
    """Aggregate streaming deltas into one assistant string."""
    messages = [
        {"role": "system", "content": "You follow instructions precisely."},
        {"role": "user", "content": user_message},
    ]
    parts: list[str] = []
    async for chunk in gateway.chat(model=model, messages=messages):
        for ch in chunk.choices:
            parts.append(ch.delta)
    return "".join(parts)
