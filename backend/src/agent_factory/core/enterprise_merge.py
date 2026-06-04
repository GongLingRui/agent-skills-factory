"""Merge Skill enterprise.yaml dict with agent.yaml enterprise (docs/04, docs/07)."""

from __future__ import annotations

from typing import Any


def merge_enterprise_configs(
    skill_enterprise: dict[str, Any] | None,
    agent_enterprise: dict[str, Any] | None,
) -> dict[str, Any]:
    """Deep-merge enterprise layers: agent overrides / extends skill defaults.

    Rules:
    - Top-level scalars: agent wins.
    - ``risk_tier_prompt_map``: per-tier lists are extended (skill first, agent
      appended) unless agent replaces a tier with a non-list (then agent wins).
    - ``prompts``: concatenated lists (skill then agent).
    - Other nested dicts: one-level shallow merge with agent keys winning.

    Args:
        skill_enterprise: Parsed enterprise.yaml (or equivalent) from Skill.
        agent_enterprise: ``agent.yaml`` ``enterprise`` block.

    Returns:
        Merged mapping (new dict).
    """
    base = dict(skill_enterprise or {})
    if not agent_enterprise:
        return base

    overlay = dict(agent_enterprise)
    for key, val in overlay.items():
        if key == "risk_tier_prompt_map":
            base[key] = _merge_tier_prompt_maps(base.get(key), val)
        elif key == "prompts":
            base[key] = _merge_prompt_lists(base.get(key), val)
        elif isinstance(val, dict) and isinstance(base.get(key), dict):
            merged_inner = dict(base[key])
            merged_inner.update(val)
            base[key] = merged_inner
        else:
            base[key] = val
    return base


def _merge_tier_prompt_maps(
    skill_map: Any,
    agent_map: Any,
) -> dict[str, Any]:
    """Merge risk_tier_prompt_map tier entries."""
    out: dict[str, Any] = {}
    if isinstance(skill_map, dict):
        for k, v in skill_map.items():
            out[str(k).lower()] = v
    if not isinstance(agent_map, dict):
        return out
    for tier_key, agent_val in agent_map.items():
        tk = str(tier_key).lower()
        skill_val = out.get(tk)
        if isinstance(skill_val, list) and isinstance(agent_val, list):
            out[tk] = list(skill_val) + list(agent_val)
        else:
            out[tk] = agent_val
    return out


def _merge_prompt_lists(skill_prompts: Any, agent_prompts: Any) -> list[str]:
    left: list[str] = []
    if isinstance(skill_prompts, list):
        left = [str(x) for x in skill_prompts]
    right: list[str] = []
    if isinstance(agent_prompts, list):
        right = [str(x) for x in agent_prompts]
    return left + right
