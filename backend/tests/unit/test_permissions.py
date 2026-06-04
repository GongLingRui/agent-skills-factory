"""Tests for permission intersection logic."""

from agent_factory.core.permissions import intersect_retrieval_scopes, intersect_tools


def test_intersect_tools_basic():
    result = intersect_tools(
        agent_tools=["a", "b", "c"],
        skill_tools=["b", "c", "d"],
        user_permissions=["b", "c"],
        department_permissions=None,
        gateway_available=["b", "c", "e"],
    )
    assert result == ["b", "c"]


def test_intersect_tools_empty():
    result = intersect_tools(
        agent_tools=["a"],
        skill_tools=["b"],
        user_permissions=None,
        department_permissions=None,
        gateway_available=None,
    )
    assert result == []


def test_intersect_tools_none_sets():
    result = intersect_tools(None, None, None, None, None)
    assert result == []


def test_intersect_tools_no_declarative_uses_gateway_catalog():
    """When agent/skill/dept omit tools, allow full gateway list (P0 built-ins)."""
    result = intersect_tools(
        None,
        None,
        None,
        None,
        gateway_available=["doc.extract", "kb.search", "z.extra"],
    )
    assert result == ["doc.extract", "kb.search", "z.extra"]


def test_intersect_tools_ignores_rbac_only_user_permissions():
    """RBAC codes must not wipe tool allowlist when not tool ids."""
    result = intersect_tools(
        agent_tools=["doc.extract", "kb.search"],
        skill_tools=None,
        user_permissions=["agent.read", "agent.admin", "agent.write"],
        department_permissions=None,
        gateway_available=["doc.extract", "kb.search", "read_reference"],
    )
    assert result == ["doc.extract", "kb.search"]


def test_intersect_tools_user_tool_grant_still_restricts():
    result = intersect_tools(
        agent_tools=["doc.extract", "kb.search"],
        skill_tools=None,
        user_permissions=["agent.read", "kb.search"],
        department_permissions=None,
        gateway_available=["doc.extract", "kb.search", "read_reference"],
    )
    assert result == ["kb.search"]


def test_intersect_retrieval_scopes():
    result = intersect_retrieval_scopes(
        agent_scopes=["s1", "s2"],
        skill_scopes=["s2", "s3"],
        user_domains=["s2"],
    )
    assert result == ["s2"]


def test_intersect_retrieval_scopes_no_overlap():
    result = intersect_retrieval_scopes(
        agent_scopes=["s1"],
        skill_scopes=["s2"],
        user_domains=["s3"],
    )
    assert result == []


def test_intersect_retrieval_explicit_empty_user_domains_denies():
    """Explicit ``user_domains=[]`` intersects with empty set (docs/07)."""
    result = intersect_retrieval_scopes(
        agent_scopes=["s1"],
        skill_scopes=["s1"],
        user_domains=[],
    )
    assert result == []
