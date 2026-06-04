"""Invariants from docs/34-p0-delivery-spec.md (Compiler / RunSpec)."""

from agent_factory.core.compiler import compile_runspec
from agent_factory.core.user_context import UserContext


def test_script_hooks_always_empty_dict():
    agent_app = {
        "id": "a",
        "version": "1.0.0",
        "instruction": "x",
        "skill_config": {"id": "s"},
        "tools_allow": ["kb.search"],
        "knowledge_scopes": ["k1"],
        "audit_config": {"level": "minimal"},
    }
    skill_pkg = {
        "id": "s",
        "version": "1.0.0",
        "skill_body": "body",
        "enterprise": {"scripts": {"preprocess": ["would-be-ignored"]}},
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": ["k1"]},
    }
    ctx = UserContext(
        session_id="sess",
        user_id_hash="u1",
        department=None,
        permissions=(),
    )
    out = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg,
        platform_policy=None,
        org_policy=None,
        user_ctx=ctx,
        available_tools=["kb.search"],
        user_data_domains=None,
    )
    assert out["script_hooks"] == {}
    assert out["audit"]["level"] == "minimal"


def test_audit_level_defaults_to_minimal():
    agent_app = {
        "id": "a2",
        "version": "1.0.0",
        "skill_config": {"id": "s"},
        "tools_allow": ["kb.search"],
        "knowledge_scopes": [],
    }
    skill_pkg = {
        "id": "s",
        "version": "1.0.0",
        "skill_body": "b",
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": []},
    }
    ctx = UserContext("x", "u", None, ())
    out = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg,
        platform_policy=None,
        org_policy=None,
        user_ctx=ctx,
        available_tools=["kb.search"],
    )
    assert out["audit"]["level"] == "minimal"
