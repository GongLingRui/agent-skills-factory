"""Map Skill ORM row to ``skill_pkg`` for :mod:`agent_factory.core.compiler`."""

from __future__ import annotations

from typing import Any

from agent_factory.db.models.skill import Skill


def _skill_instruction_body(skill: Skill, meta: dict[str, Any]) -> str:
    """Prefer package_metadata instruction; else name + description + when_to_use."""
    for key in ("skill_instruction", "skill_body"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    parts: list[str] = []
    if skill.name:
        parts.append(f"# {skill.name}")
    if skill.description:
        parts.append(skill.description)
    if skill.when_to_use:
        parts.append(skill.when_to_use)
    return "\n\n".join(parts)


def skill_orm_to_compiler_pkg(skill: Skill) -> dict[str, Any]:
    """Build ``skill_pkg`` for ``compile_runspec``.

    Scalar columns hold discovery metadata; ``package_metadata`` stores the Skill
    bundle fields required at compile time (enterprise block, tools, scopes,
    reference manifests). Missing keys use Compiler-safe defaults.
    """
    raw = skill.package_metadata
    meta: dict[str, Any] = raw if isinstance(raw, dict) else {}

    tools_raw = meta.get("tools")
    if isinstance(tools_raw, dict):
        tools = {
            "require": list(tools_raw.get("require") or []),
            "optional": list(tools_raw.get("optional") or []),
        }
    else:
        tools = {"require": [], "optional": []}

    ks_raw = meta.get("knowledge_scopes")
    if isinstance(ks_raw, dict):
        knowledge_scopes = {"suggest": list(ks_raw.get("suggest") or [])}
    else:
        knowledge_scopes = {"suggest": []}

    ent = meta.get("enterprise")
    enterprise: dict[str, Any] = ent if isinstance(ent, dict) else {}

    def _dict_list(key: str) -> list[dict[str, Any]]:
        v = meta.get(key)
        if not isinstance(v, list):
            return []
        out: list[dict[str, Any]] = []
        for item in v:
            if isinstance(item, dict):
                out.append(dict(item))
        return out

    fm = meta.get("file_manifest")
    file_manifest: dict[str, Any] = fm if isinstance(fm, dict) else {}

    return {
        "id": skill.id,
        "version": skill.version,
        "risk_tier": skill.risk_tier,
        "skill_body": _skill_instruction_body(skill, meta),
        "enterprise": enterprise,
        "tools": tools,
        "knowledge_scopes": knowledge_scopes,
        "always_refs": _dict_list("always_refs"),
        "lazy_refs": _dict_list("lazy_refs"),
        "indexed_refs": _dict_list("indexed_refs"),
        "file_manifest": file_manifest,
    }
