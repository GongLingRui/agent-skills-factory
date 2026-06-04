"""Permission intersection for Compiler (docs/07)."""

from __future__ import annotations


def intersect_tools(
    agent_tools: list[str] | None,
    skill_tools: list[str] | None,
    user_permissions: list[str] | None,
    department_permissions: list[str] | None,
    gateway_available: list[str] | None,
) -> list[str]:
    """Compute allowed_tools = intersection of all sets.

    JWT ``permissions`` may mix RBAC codes (e.g. ``agent.read``) with tool ids
    (e.g. ``doc.extract``). Only values present in ``gateway_available`` count
    as tool grants; pure RBAC tokens are ignored so role-only sessions still
    follow agent/skill tool policy.
    """
    gw_set = set(gateway_available or [])
    sets: list[set[str]] = []
    for arr in (agent_tools, skill_tools, department_permissions):
        if arr:
            sets.append(set(arr))
    if user_permissions and gw_set:
        toolish = {p for p in user_permissions if p in gw_set}
        if toolish:
            sets.append(toolish)
    if not sets:
        # No agent/skill/dept/user tool grant: treat as unconstrained → all
        # gateway-registered tools (built-ins in P0). Early ``return []`` here
        # incorrectly produced empty RunSpec.allowed_tools for many agents.
        return sorted(gw_set) if gw_set else []
    if gw_set:
        sets.append(gw_set)
    result = sets[0]
    for s in sets[1:]:
        result &= s
    return sorted(result)


def intersect_retrieval_scopes(
    agent_scopes: list[str] | None,
    skill_scopes: list[str] | None,
    user_domains: list[str] | None,
) -> list[str]:
    """Compute retrieval_scopes = intersection of all sets."""
    sets: list[set[str]] = []
    for arr in (agent_scopes, skill_scopes):
        if arr:
            sets.append(set(arr))
    if user_domains is not None:
        sets.append(set(user_domains))
    if not sets:
        return []
    result = sets[0]
    for s in sets[1:]:
        result &= s
    return sorted(result)
