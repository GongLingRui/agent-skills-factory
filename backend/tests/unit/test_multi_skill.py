"""Tests for multi-skill intersection merge."""

from __future__ import annotations

from agent_factory.core.multi_skill import (
    merge_secondary_skill_packages,
    parse_secondary_skill_refs,
)
from agent_factory.core.user_context import UserContext


def test_parse_secondary_refs():
    agent = {
        "skill_config": {
            "id": "primary",
            "secondary_skills": [
                {"id": "sec-a", "version": "1.0.0"},
                "sec-b",
            ],
        }
    }
    refs = parse_secondary_skill_refs(agent)
    assert len(refs) == 2
    assert refs[0]["id"] == "sec-a"


def test_merge_intersects_tools():
    primary = {
        "id": "p",
        "tools": {"require": ["kb.search", "doc.extract"], "optional": []},
        "knowledge_scopes": {"suggest": ["a", "b"]},
    }
    secondary = {
        "id": "s",
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": ["a"]},
    }
    ctx = UserContext("sess", "u", None, ())
    merged, ids = merge_secondary_skill_packages(
        primary,
        [secondary],
        agent_app={"tools_allow": ["kb.search", "doc.extract"], "knowledge_scopes": ["a", "b"]},
        user_ctx=ctx,
        gateway_available=["kb.search", "doc.extract"],
        user_data_domains=["a", "b"],
    )
    assert "kb.search" in merged["_merged_allowed_tools"]
    assert "doc.extract" not in merged["_merged_allowed_tools"]
    assert ids == ["p", "s"]
