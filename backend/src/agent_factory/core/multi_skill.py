"""Multi-skill RunSpec merge: tool/scope intersection (prd P3)."""

from __future__ import annotations

from typing import Any

from agent_factory.core.permissions import (
    intersect_retrieval_scopes,
    intersect_tools,
)
from agent_factory.core.user_context import UserContext


def parse_secondary_skill_refs(
    agent_app: dict[str, Any],
) -> list[dict[str, str]]:
    cfg = agent_app.get("skill_config")
    if not isinstance(cfg, dict):
        return []
    raw = cfg.get("secondary_skills")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            out.append({"id": item.strip(), "version": ""})
            continue
        if isinstance(item, dict):
            sid = str(item.get("id") or item.get("skill_id") or "").strip()
            ver = str(item.get("version") or "").strip()
            if sid:
                out.append({"id": sid, "version": ver})
    return out


def merge_secondary_skill_packages(
    primary_skill: dict[str, Any],
    secondary_pkgs: list[dict[str, Any]],
    *,
    agent_app: dict[str, Any],
    user_ctx: UserContext,
    gateway_available: list[str],
    user_data_domains: list[str] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Intersect tools/scopes across primary + secondaries; annotate runtime."""
    agent_tools = agent_app.get("tools_allow") or []
    scopes_acc: list[str] | None = None
    tools_acc: list[str] | None = None
    skill_ids: list[str] = [str(primary_skill.get("id", ""))]

    def _fold(skill_pkg: dict[str, Any]) -> None:
        nonlocal scopes_acc, tools_acc
        st = (skill_pkg.get("tools") or {}).get("require", []) + (
            (skill_pkg.get("tools") or {}).get("optional", [])
        )
        ss = (skill_pkg.get("knowledge_scopes") or {}).get("suggest", [])
        tools_acc = (
            intersect_tools(
                agent_tools=agent_tools,
                skill_tools=st,
                user_permissions=list(user_ctx.permissions) if user_ctx.permissions else None,
                department_permissions=None,
                gateway_available=gateway_available,
            )
            if tools_acc is None
            else intersect_tools(
                agent_tools=tools_acc,
                skill_tools=st,
                user_permissions=None,
                department_permissions=None,
                gateway_available=gateway_available,
            )
        )
        scopes_acc = (
            intersect_retrieval_scopes(
                agent_scopes=agent_app.get("knowledge_scopes"),
                skill_scopes=ss,
                user_domains=user_data_domains,
            )
            if scopes_acc is None
            else intersect_retrieval_scopes(
                agent_scopes=scopes_acc,
                skill_scopes=ss,
                user_domains=user_data_domains,
            )
        )

    _fold(primary_skill)
    for pkg in secondary_pkgs:
        skill_ids.append(str(pkg.get("id", "")))
        _fold(pkg)

    primary_skill = dict(primary_skill)
    if tools_acc is not None:
        primary_skill["_merged_allowed_tools"] = tools_acc
    if scopes_acc is not None:
        primary_skill["_merged_retrieval_scopes"] = scopes_acc
    primary_skill["_multi_skill_ids"] = [x for x in skill_ids if x]
    return primary_skill, skill_ids
