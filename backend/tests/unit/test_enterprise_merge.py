"""Tests for enterprise config merge (docs/04, docs/07)."""

from agent_factory.core.compiler import compile_runspec
from agent_factory.core.enterprise_merge import merge_enterprise_configs
from agent_factory.core.prompt_builder import resolve_risk_tier_prompt
from agent_factory.core.user_context import UserContext


def test_merge_enterprise_tier_map_extends():
    skill = {
        "risk_tier_prompt_map": {
            "medium": ["skill line"],
        },
    }
    agent = {
        "risk_tier_prompt_map": {
            "medium": ["agent line"],
        },
    }
    merged = merge_enterprise_configs(skill, agent)
    assert merged["risk_tier_prompt_map"]["medium"] == [
        "skill line",
        "agent line",
    ]


def test_merge_enterprise_prompts_concat():
    merged = merge_enterprise_configs(
        {"prompts": ["a"]},
        {"prompts": ["b"]},
    )
    assert merged["prompts"] == ["a", "b"]


def test_resolve_agent_override_wins_over_skill_map():
    merged = merge_enterprise_configs(
        {"risk_tier_prompt_map": {"low": ["from skill"]}},
        {},
    )
    text = resolve_risk_tier_prompt(
        "low",
        merged_enterprise=merged,
        agent_enterprise={
            "risk_tier_prompt_override": {"low": ["agent override"]},
        },
    )
    assert text == "agent override"


def test_compile_agent_enterprise_overrides_risk_tier():
    agent_app = {
        "id": "a1",
        "enterprise_config": {"risk_tier": "high"},
        "tools_allow": ["kb.search"],
        "knowledge_scopes": ["s1"],
    }
    skill_pkg = {
        "id": "sk",
        "enterprise": {"risk_tier": "low"},
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": ["s1"]},
    }
    user_ctx = UserContext(
        session_id="s",
        user_id_hash="u",
        department=None,
        permissions=(),
    )
    result = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg,
        platform_policy=None,
        org_policy=None,
        user_ctx=user_ctx,
        available_tools=["kb.search"],
    )
    risk_part = next(p for p in result["prompt_parts"] if p["role"] == "risk_tier")
    assert "【风险等级：高】" in risk_part["content"]
