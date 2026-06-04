"""Tests for SessionMemory Pydantic schema."""

from __future__ import annotations

import pytest

from agent_factory.core.session_memory_schema import SessionMemory, render_for_prompt


def test_session_memory_empty():
    mem = SessionMemory()
    assert mem.is_empty() is True


def test_session_memory_fields():
    mem = SessionMemory(
        facts=["fact1"],
        preferences=["pref1"],
        decisions=["dec1"],
        todos=["todo1"],
        terms=[{"name": "AI", "definition": "人工智能"}],
    )
    assert mem.is_empty() is False
    assert mem.facts == ["fact1"]
    assert mem.terms[0]["name"] == "AI"


def test_render_for_prompt():
    mem = SessionMemory(
        facts=["fact1"],
        preferences=[],
        decisions=["dec1"],
        todos=["todo1"],
        terms=[{"name": "AI", "definition": "人工智能"}],
    )
    out = render_for_prompt(mem)
    assert "关键事实" in out
    assert "已确认决定" in out
    assert "待办事项" in out
    assert "专有名词" in out
    assert "AI" in out


def test_render_for_prompt_raw_text_fallback():
    mem = SessionMemory(raw_text="Some raw text")
    out = render_for_prompt(mem)
    assert "Some raw text" in out


def test_render_for_prompt_empty():
    assert render_for_prompt(SessionMemory()) == ""
