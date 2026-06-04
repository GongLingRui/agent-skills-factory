"""Tests for Skill ORM → compile_runspec payload mapping."""

from agent_factory.db.models.skill import Skill
from agent_factory.services.skill_payload import skill_orm_to_compiler_pkg


def test_skill_orm_to_compiler_pkg_defaults():
    row = Skill(
        id="s1",
        version="0.1.0",
        when_to_use="body",
        risk_tier="low",
    )
    pkg = skill_orm_to_compiler_pkg(row)
    assert pkg["id"] == "s1"
    assert pkg["skill_body"] == "body"
    assert pkg["enterprise"] == {}
    assert pkg["tools"] == {"require": [], "optional": []}
    assert pkg["knowledge_scopes"] == {"suggest": []}


def test_skill_orm_to_compiler_pkg_from_metadata():
    row = Skill(
        id="s1",
        version="0.1.0",
        risk_tier="medium",
        package_metadata={
            "enterprise": {"risk_tier": "high", "prompts": ["extra"]},
            "tools": {"require": ["kb.search"], "optional": []},
            "knowledge_scopes": {"suggest": ["scope_a"]},
            "always_refs": [{"name": "r1", "content": "c"}],
        },
    )
    pkg = skill_orm_to_compiler_pkg(row)
    assert pkg["enterprise"]["risk_tier"] == "high"
    assert pkg["tools"]["require"] == ["kb.search"]
    assert pkg["knowledge_scopes"]["suggest"] == ["scope_a"]
    assert pkg["always_refs"][0]["name"] == "r1"


def test_skill_orm_skill_body_prefers_package_metadata_instruction():
    row = Skill(
        id="s1",
        version="0.1.0",
        name="N",
        description="D",
        when_to_use="W",
        risk_tier="low",
        package_metadata={"skill_instruction": "INSTR only"},
    )
    pkg = skill_orm_to_compiler_pkg(row)
    assert pkg["skill_body"] == "INSTR only"


def test_skill_orm_skill_body_composes_from_columns_when_no_meta():
    row = Skill(
        id="s1",
        version="0.1.0",
        name="My Skill",
        description="Desc line",
        when_to_use="When to use line",
        risk_tier="low",
    )
    pkg = skill_orm_to_compiler_pkg(row)
    assert "# My Skill" in pkg["skill_body"]
    assert "Desc line" in pkg["skill_body"]
    assert "When to use line" in pkg["skill_body"]
