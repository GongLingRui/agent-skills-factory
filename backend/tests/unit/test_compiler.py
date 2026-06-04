"""Tests for Skill Compiler pure functions."""

from agent_factory.core.compiler import compile_runspec
from agent_factory.core.user_context import UserContext


def test_compile_runspec_basic():
    agent_app = {
        "id": "test-agent",
        "version": "0.1.0",
        "model_policy": {"default": "qwen3-32b"},
        "skill_config": {"id": "test-skill"},
        "tools_allow": ["kb.search"],
        "knowledge_scopes": ["scope1"],
        "limits_config": {"max_turns": 3},
        "audit_config": {},
    }
    skill_pkg = {
        "id": "test-skill",
        "version": "0.1.0",
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": ["scope1"]},
        "enterprise": {"risk_tier": "medium"},
        "skill_body": "Do things",
    }
    user_ctx = UserContext(
        session_id="sess_1",
        user_id_hash="u123",
        department="legal",
        permissions=(),
    )
    result = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg,
        platform_policy="platform",
        org_policy="org",
        user_ctx=user_ctx,
        available_tools=["kb.search"],
    )
    assert result["runspec_schema_version"] == 1
    assert result["agent_id"] == "test-agent"
    assert result["skill_id"] == "test-skill"
    assert result["script_hooks"] == {}
    assert "run_" in result["run_id"]
    assert result["allowed_tools"] == ["kb.search"]
    assert result["retrieval_scopes"] == ["scope1"]
    assert result["runtime"]["max_turns"] == 3
    assert "context_memory" not in result["runtime"]
    assert result["audit"]["level"] == "minimal"
    prompt_roles = [p["role"] for p in result["prompt_parts"]]
    assert "platform_policy" in prompt_roles
    assert "risk_tier" in prompt_roles


def test_compile_runspec_context_memory_in_runtime():
    agent_app = {
        "id": "ctx-agent",
        "version": "0.1.0",
        "model_policy": {"default": "MiniMax-M2.7"},
        "skill_config": {"id": "sk"},
        "tools_allow": ["kb.search"],
        "knowledge_scopes": [],
        "limits_config": {
            "max_turns": 6,
            "context_memory": {
                "keep_recent_user_turns": 6,
                "enabled": True,
            },
        },
        "audit_config": {},
    }
    skill_pkg = {
        "id": "sk",
        "version": "0.1.0",
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": []},
        "enterprise": {},
        "skill_body": "x",
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
    assert result["runtime"]["context_memory"]["keep_recent_user_turns"] == 6


def test_compile_runspec_runtime_override_model():
    agent_app = {
        "id": "m",
        "version": "0.1.0",
        "model_policy": {"default": "MiniMax-M2.7", "fallback": "MiniMax-M2.7"},
        "skill_config": {"id": "sk"},
        "tools_allow": ["kb.search"],
        "knowledge_scopes": [],
        "limits_config": {},
        "audit_config": {},
    }
    skill_pkg = {
        "id": "sk",
        "version": "0.1.0",
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": []},
        "enterprise": {},
        "skill_body": "x",
    }
    user_ctx = UserContext(
        session_id="s", user_id_hash="u", department=None, permissions=()
    )
    result = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg,
        platform_policy=None,
        org_policy=None,
        user_ctx=user_ctx,
        available_tools=["kb.search"],
        runtime_overrides={"model": "qwen3-8b"},
    )
    assert result["runtime"]["model"] == "qwen3-8b"


def test_compile_runspec_no_tools():
    agent_app = {"id": "a", "tools_allow": ["t1"], "knowledge_scopes": ["s1"]}
    skill_pkg = {
        "tools": {"require": ["t2"]},
        "knowledge_scopes": {"suggest": ["s2"]},
        "enterprise": {},
    }
    user_ctx = UserContext(
        session_id="s", user_id_hash="u", department=None, permissions=()
    )
    result = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg,
        platform_policy=None,
        org_policy=None,
        user_ctx=user_ctx,
        available_tools=["t3"],
    )
    assert result["allowed_tools"] == []
    assert result["retrieval_scopes"] == []


def test_compile_runspec_null_model_policy_from_db():
    """JSONB null is deserialized as None; compiler must not crash."""
    agent_app = {
        "id": "demo",
        "version": "1",
        "model_policy": None,
        "limits_config": None,
        "audit_config": None,
        "skill_config": {"id": "sk"},
        "tools_allow": ["kb.search"],
        "knowledge_scopes": [],
    }
    skill_pkg = {
        "id": "sk",
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": []},
        "enterprise": {},
    }
    user_ctx = UserContext(
        session_id="s", user_id_hash="u", department=None, permissions=()
    )
    result = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg,
        platform_policy=None,
        org_policy=None,
        user_ctx=user_ctx,
        available_tools=["kb.search"],
    )
    assert result["runtime"]["model"] == "MiniMax-M2.7"
    assert result["runtime"]["max_turns"] == 6
    assert result["audit"]["level"] == "minimal"


def test_compile_runspec_skill_package_hash_stable_with_manifest():
    """Hash is deterministic and includes file_manifest (prd §7.7)."""
    agent_app = {
        "id": "a",
        "version": "1",
        "skill_config": {"id": "sk"},
        "tools_allow": ["kb.search"],
        "knowledge_scopes": [],
        "limits_config": {},
        "audit_config": {},
    }
    skill_pkg = {
        "id": "sk",
        "version": "1.0.0",
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": []},
        "enterprise": {},
        "skill_body": "body",
        "file_manifest": {"b.md": "h2", "a.md": "h1"},
    }
    user_ctx = UserContext(
        session_id="s", user_id_hash="u", department=None, permissions=()
    )
    r1 = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg,
        platform_policy=None,
        org_policy=None,
        user_ctx=user_ctx,
        available_tools=["kb.search"],
    )
    skill_pkg2 = {
        **skill_pkg,
        "file_manifest": {"a.md": "h1", "b.md": "h2"},
    }
    r2 = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg2,
        platform_policy=None,
        org_policy=None,
        user_ctx=user_ctx,
        available_tools=["kb.search"],
    )
    assert r1["skill_package_hash"] == r2["skill_package_hash"]
    skill_pkg3 = {**skill_pkg, "file_manifest": {"a.md": "h1"}}
    r3 = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg3,
        platform_policy=None,
        org_policy=None,
        user_ctx=user_ctx,
        available_tools=["kb.search"],
    )
    assert r1["skill_package_hash"] != r3["skill_package_hash"]


def test_compile_runspec_output_schema_from_merged_enterprise():
    agent_app = {
        "id": "a",
        "version": "1",
        "skill_config": {"id": "sk"},
        "tools_allow": ["kb.search"],
        "knowledge_scopes": [],
        "enterprise_config": {"output_schema": "ent_schema"},
    }
    skill_pkg = {
        "id": "sk",
        "version": "1.0.0",
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": []},
        "enterprise": {},
    }
    user_ctx = UserContext(
        session_id="s", user_id_hash="u", department=None, permissions=()
    )
    result = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg,
        platform_policy=None,
        org_policy=None,
        user_ctx=user_ctx,
        available_tools=["kb.search"],
    )
    assert result["output_schema"] == "ent_schema"


def test_compile_runspec_agent_output_schema_overrides_enterprise():
    agent_app = {
        "id": "a",
        "version": "1",
        "skill_config": {"id": "sk"},
        "tools_allow": ["kb.search"],
        "knowledge_scopes": [],
        "output_schema": "agent_schema",
        "enterprise_config": {"output_schema": "ent_schema"},
    }
    skill_pkg = {
        "id": "sk",
        "version": "1.0.0",
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": []},
        "enterprise": {},
    }
    user_ctx = UserContext(
        session_id="s", user_id_hash="u", department=None, permissions=()
    )
    result = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg,
        platform_policy=None,
        org_policy=None,
        user_ctx=user_ctx,
        available_tools=["kb.search"],
    )
    assert result["output_schema"] == "agent_schema"


def test_compile_runspec_runspec_schema_version_from_agent():
    agent_app = {
        "id": "a",
        "version": "1",
        "skill_config": {"id": "sk"},
        "tools_allow": ["kb.search"],
        "knowledge_scopes": [],
        "runspec_schema_version": 2,
    }
    skill_pkg = {
        "id": "sk",
        "version": "1.0.0",
        "tools": {"require": ["kb.search"], "optional": []},
        "knowledge_scopes": {"suggest": []},
        "enterprise": {},
    }
    user_ctx = UserContext(
        session_id="s", user_id_hash="u", department=None, permissions=()
    )
    result = compile_runspec(
        agent_app=agent_app,
        skill_pkg=skill_pkg,
        platform_policy=None,
        org_policy=None,
        user_ctx=user_ctx,
        available_tools=["kb.search"],
    )
    assert result["runspec_schema_version"] == 2
