"""Prompt assembly for Skill Compiler (docs/07)."""

from __future__ import annotations

from typing import Any

_RISK_TIER_DEFAULT_MAP: dict[str, str] = {
    "low": "【风险等级：低】请按常规流程处理，无需额外审批标注。",
    "medium": (
        "【风险等级：中】输出涉及业务判断时，必须标注\"需人工复核\"。"
        "引用制度时必须标注文号和生效日期。"
    ),
    "high": (
        "【风险等级：高】所有输出必须标注\"需人工复核\"，不得替代专业判断。"
        "涉及金额、期限、权利义务的结论必须列出依据来源。"
        "不确定时必须明确拒绝回答，禁止编造依据。"
    ),
}


def resolve_risk_tier_prompt(
    risk_tier: str | None,
    *,
    merged_enterprise: dict[str, Any],
    agent_enterprise: dict[str, Any] | None,
) -> str | None:
    """Resolve governance text for ``risk_tier`` (docs/07 §risk_tier 映射规则).

    Order:
    1. ``agent_enterprise.risk_tier_prompt_override`` map (full agent map).
    2. ``merged_enterprise.risk_tier_prompt_map`` (skill YAML merged with agent).
    3. Built-in defaults.

    For ``high`` tier, append mandatory phrases if an override omits them.
    """
    if not risk_tier:
        return None
    tier_key = risk_tier.lower()
    agent_ent = agent_enterprise or {}

    override_map = agent_ent.get("risk_tier_prompt_override")
    if isinstance(override_map, dict) and override_map:
        text = _lookup_tier_prompt_map(override_map, tier_key)
        if text:
            return _ensure_high_tier_mandates(text, tier_key)

    merged_map = merged_enterprise.get("risk_tier_prompt_map")
    if isinstance(merged_map, dict) and merged_map:
        text = _lookup_tier_prompt_map(merged_map, tier_key)
        if text:
            return text

    return _RISK_TIER_DEFAULT_MAP.get(tier_key)


def _lookup_tier_prompt_map(mapping: dict[str, Any], tier_key: str) -> str | None:
    raw = mapping.get(tier_key)
    if raw is None:
        raw = mapping.get(tier_key.upper())
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw.strip() or None
    if isinstance(raw, list):
        lines = [str(x).strip() for x in raw if str(x).strip()]
        if not lines:
            return None
        return "\n".join(lines)
    return str(raw)


def _ensure_high_tier_mandates(text: str, tier_key: str) -> str:
    """Agent override cannot drop mandatory high-tier phrases (docs/07)."""
    if tier_key != "high":
        return text
    missing: list[str] = []
    if "需人工复核" not in text:
        missing.append("必须标注「需人工复核」")
    if "禁止编造" not in text and "编造依据" not in text:
        missing.append("禁止编造依据")
    if not missing:
        return text
    return text + "\n【高风险强制】" + "；".join(missing) + "。"


def build_prompt_parts(
    *,
    platform_policy: str | None,
    org_policy: str | None,
    agent_instruction: str | None,
    risk_tier_prompt: str | None,
    enterprise_prompts: list[str] | None,
    skill_body: str | None,
    always_refs: list[dict[str, str]] | None,
    lazy_refs: list[dict[str, str]] | None,
    indexed_refs: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """Assemble prompt_parts in priority order (docs/07 §5)."""
    parts: list[dict[str, str]] = []

    if platform_policy:
        parts.append({"role": "platform_policy", "content": platform_policy})
    if org_policy:
        parts.append({"role": "org_policy", "content": org_policy})
    if agent_instruction:
        parts.append({"role": "agent_instruction", "content": agent_instruction})

    if risk_tier_prompt:
        parts.append({"role": "risk_tier", "content": risk_tier_prompt})

    if enterprise_prompts:
        for idx, ep in enumerate(enterprise_prompts):
            parts.append({"role": f"enterprise_prompt_{idx}", "content": ep})

    if skill_body:
        parts.append({"role": "skill_instruction", "content": skill_body})

    if always_refs:
        for ref in always_refs:
            parts.append(
                {
                    "role": "always_reference",
                    "content": (
                        f"<{ref['name']}>\n"
                        f"{ref.get('content', '')}\n"
                        f"</{ref['name']}>"
                    ),
                }
            )

    if lazy_refs:
        lines: list[str] = [
            "以下 Skill reference 需通过 read_reference 工具按需加载。"
            "调用时 name 参数只能使用下列名称（不要带 references/ 路径或 .md 等后缀）：",
        ]
        for r in lazy_refs:
            if isinstance(r, dict) and r.get("name"):
                path = r.get("path", "")
                lines.append(f"- {r['name']}" + (f" ({path})" if path else ""))
        parts.append({"role": "lazy_references", "content": "\n".join(lines)})

    if indexed_refs:
        idx_text = "\n".join(
            f"- {r['name']}: scope={r.get('scope', '')}" for r in indexed_refs
        )
        parts.append({"role": "indexed_references", "content": idx_text})

    return parts
