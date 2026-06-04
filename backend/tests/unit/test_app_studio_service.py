"""Tests for app studio compose helpers."""

from agent_factory.services.app_studio_service import (
    SkillCatalogEntry,
    _build_agent_body,
    _default_skill_body,
    _extract_new_skill_spec,
    _llm_has_rich_new_skill,
    find_best_skill_match,
    skill_match_is_confident,
)


def _entry(
    sid: str,
    *,
    name: str = "",
    desc: str = "",
    when: str = "",
) -> SkillCatalogEntry:
    return SkillCatalogEntry(
        id=sid,
        version="0.1.0",
        name=name or sid,
        description=desc,
        when_to_use=when,
    )


def test_find_best_skill_match_keywords():
    catalog = [
        _entry("demo-skill", name="Demo", desc="smoke test"),
        _entry(
            "problem-essence-analyst",
            name="问题本质分析",
            desc="根因与组织模式诊断",
            when="部门推诿、指标博弈、组织 dysfunction",
        ),
    ]
    match = find_best_skill_match(
        "我们部门互相推诿，KPI 造假，需要做组织根因分析",
        catalog,
    )
    assert match.skill is not None
    assert match.skill.id == "problem-essence-analyst"
    assert skill_match_is_confident(match)


def test_no_confident_match_for_unrelated_requirements():
    catalog = [
        _entry("demo-skill", name="Demo", desc="smoke test"),
        _entry(
            "problem-essence-analyst",
            name="问题本质分析",
            desc="根因与组织模式诊断",
            when="部门推诿",
        ),
    ]
    match = find_best_skill_match(
        "帮我做一个儿童绘本故事生成器，要有插画描述和分镜",
        catalog,
    )
    assert not skill_match_is_confident(match)


def test_build_agent_body_includes_skill_and_ui():
    skill = _entry("demo-skill", name="Demo Skill", desc="For tests")
    body = _build_agent_body(
        requirements="帮我做一个会议纪要助手",
        skill=skill,
        agent_id="demo-skill-app-deadbe",
        llm=None,
    )
    assert body["id"] == "demo-skill-app-deadbe"
    assert body["skill"]["id"] == "demo-skill"
    assert body["ui_config"]["title"]
    assert "read_reference" in body["tools"]["allow"]


def test_extract_new_skill_spec_from_llm_nested():
    spec = _extract_new_skill_spec(
        "做一个法务合同审查助手",
        {
            "new_skill": {
                "id": "contract-review-helper",
                "name": "合同审查助手",
                "description": "审查合同条款风险",
                "when_to_use": "用户提供合同文本时",
                "skill_body": "# 合同审查\n\n按条款检查。",
            },
        },
    )
    assert spec["id_hint"] == "contract-review-helper"
    assert spec["name"] == "合同审查助手"
    assert "合同审查" in spec["skill_body"]


def test_default_skill_body_contains_requirements():
    body = _default_skill_body(
        name="测试",
        description="描述",
        when_to_use="场景",
        requirements="用户的原始需求文本",
    )
    assert "用户的原始需求文本" in body


def test_skill_match_requires_margin_over_runner_up():
    catalog = [
        _entry("skill-a", name="通用分析", desc="分析数据与文本", when="分析场景"),
        _entry("skill-b", name="通用写作", desc="分析并撰写报告", when="写作场景"),
    ]
    match = find_best_skill_match("帮我做一份数据分析报告", catalog)
    assert match.skill is not None
    assert not skill_match_is_confident(match)


def test_build_agent_body_uses_llm_tools():
    skill = _entry("demo-skill", name="Demo Skill", desc="For tests")
    body = _build_agent_body(
        requirements="合同审查",
        skill=skill,
        agent_id="demo-skill-app-deadbe",
        llm={"tools": {"allow": ["kb.search", "read_reference"]}},
    )
    assert body["tools"]["allow"] == ["kb.search", "read_reference"]


def test_llm_has_rich_new_skill():
    assert not _llm_has_rich_new_skill(None)
    assert not _llm_has_rich_new_skill({"new_skill": {"skill_body": "短"}})
    assert _llm_has_rich_new_skill(
        {"new_skill": {"skill_body": "x" * 120}}
    )
