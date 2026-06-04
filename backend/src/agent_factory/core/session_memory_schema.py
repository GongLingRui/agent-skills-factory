"""Structured session memory schema."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SessionMemory(BaseModel):
    """Per-turn extracted structured memory."""

    facts: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    todos: list[str] = Field(default_factory=list)
    terms: list[dict[str, str]] = Field(default_factory=list)
    raw_text: str = ""

    def is_empty(self) -> bool:
        return not any([
            self.facts,
            self.preferences,
            self.decisions,
            self.todos,
            self.terms,
            self.raw_text,
        ])


def render_for_prompt(memory: SessionMemory) -> str:
    """Render structured memory as formatted text for system prompt injection."""
    if memory.is_empty():
        return ""
    parts: list[str] = []
    if memory.facts:
        parts.append("关键事实：\n" + "\n".join(f"- {f}" for f in memory.facts))
    if memory.preferences:
        parts.append("用户偏好：\n" + "\n".join(f"- {p}" for p in memory.preferences))
    if memory.decisions:
        parts.append("已确认决定：\n" + "\n".join(f"- {d}" for d in memory.decisions))
    if memory.todos:
        parts.append("待办事项：\n" + "\n".join(f"- {t}" for t in memory.todos))
    if memory.terms:
        parts.append(
            "专有名词：\n"
            + "\n".join(
                f"- {t.get('name', '')}：{t.get('definition', '')}"
                for t in memory.terms
            )
        )
    if memory.raw_text and not parts:
        parts.append(memory.raw_text)
    return "\n\n".join(parts)
