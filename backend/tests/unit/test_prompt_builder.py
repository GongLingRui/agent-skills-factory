"""Tests for prompt builder."""

from agent_factory.core.prompt_builder import build_prompt_parts


def test_build_prompt_parts_minimal():
    parts = build_prompt_parts(
        platform_policy=None,
        org_policy=None,
        agent_instruction=None,
        risk_tier_prompt=None,
        enterprise_prompts=None,
        skill_body=None,
        always_refs=None,
        lazy_refs=None,
        indexed_refs=None,
    )
    assert parts == []


def test_build_prompt_parts_full():
    parts = build_prompt_parts(
        platform_policy="platform rule",
        org_policy="org rule",
        agent_instruction="agent inst",
        risk_tier_prompt=(
            "【风险等级：高】所有输出必须标注\"需人工复核\"，不得替代专业判断。"
            "涉及金额、期限、权利义务的结论必须列出依据来源。"
            "不确定时必须明确拒绝回答，禁止编造依据。"
        ),
        enterprise_prompts=["ep1"],
        skill_body="skill body",
        always_refs=[{"name": "ref1", "content": "ref content"}],
        lazy_refs=[{"name": "lazy1", "path": "p1.md"}],
        indexed_refs=[{"name": "idx1", "scope": "s1"}],
    )
    roles = [p["role"] for p in parts]
    assert roles == [
        "platform_policy",
        "org_policy",
        "agent_instruction",
        "risk_tier",
        "enterprise_prompt_0",
        "skill_instruction",
        "always_reference",
        "lazy_references",
        "indexed_references",
    ]
    assert "【风险等级：高】" in parts[3]["content"]
