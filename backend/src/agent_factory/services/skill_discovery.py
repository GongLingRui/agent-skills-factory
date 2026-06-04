"""Skill discovery: conditional activation and dynamic mounting (Stage D)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.db.models.skill import Skill

logger = logging.getLogger(__name__)


async def discover_skills_for_agent(
    db: AsyncSession,
    *,
    agent_skill_config: dict[str, Any] | None,
    user_department: str | None,
) -> list[Skill]:
    """Return dynamically matched active Skills for an agent context."""
    if not agent_skill_config:
        return []
    discovery_rules = agent_skill_config.get("discovery_rules")
    if not isinstance(discovery_rules, list):
        return []

    matched: list[Skill] = []
    seen: set[str] = set()
    for rule in discovery_rules:
        if not isinstance(rule, dict):
            continue
        dept_match = True
        target_dept = rule.get("department")
        if isinstance(target_dept, str) and target_dept.strip():
            dept_match = user_department == target_dept.strip()
        if not dept_match:
            continue

        skill_id = rule.get("skill_id")
        if not isinstance(skill_id, str) or not skill_id.strip():
            continue
        if skill_id in seen:
            continue
        seen.add(skill_id)

        q = await db.execute(
            select(Skill).where(
                Skill.id == skill_id,
                Skill.status == "active",
            )
        )
        row = q.scalar_one_or_none()
        if row is not None:
            matched.append(row)

    return matched


def expand_runspec_from_discovered_skills(
    base_tools: list[str],
    base_scopes: list[str],
    skills: list[Skill],
) -> tuple[list[str], list[str]]:
    """Extend allowed_tools and retrieval_scopes from discovered Skills."""
    extra_tools: list[str] = []
    extra_scopes: list[str] = []
    for skill in skills:
        meta = (
            skill.package_metadata
            if isinstance(skill.package_metadata, dict)
            else {}
        )
        skill_tools = (meta.get("tools") or {}).get("require", [])
        if isinstance(skill_tools, list):
            extra_tools.extend(
                str(t).strip()
                for t in skill_tools
                if isinstance(t, str)
            )
        skill_scopes = (meta.get("knowledge_scopes") or {}).get("suggest", [])
        if isinstance(skill_scopes, list):
            extra_scopes.extend(
                str(s).strip()
                for s in skill_scopes
                if isinstance(s, str)
            )

    merged_tools = list(dict.fromkeys(base_tools + extra_tools))
    merged_scopes = list(dict.fromkeys(base_scopes + extra_scopes))
    return merged_tools, merged_scopes
