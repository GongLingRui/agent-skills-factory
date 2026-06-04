"""Parse agent.yaml-shaped JSON into DB column payloads (docs/03)."""

from __future__ import annotations

import re
from typing import Any

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$|^[a-z0-9]$")


def validate_agent_id(agent_id: str) -> None:
    """Raise ValueError when id does not match declarative agent id rules."""
    if not agent_id or not _ID_PATTERN.match(agent_id):
        raise ValueError(
            "id must be lowercase letters, digits, hyphens; "
            "length 1–64 and cannot start/end with hyphen"
        )


def normalize_agent_yaml_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Map YAML / JSON body keys to agent_apps column names.

    Accepts nested ``release`` / ``tools.allow`` blocks, flat ``tools_allow``,
    and flat ``release`` aliases; ``tools.allow`` overrides ``tools_allow``.
    """
    skill_block = data.get("skill") or {}
    if not isinstance(skill_block, dict):
        raise ValueError("skill must be an object")

    tools_block = data.get("tools") or {}
    tools_allow: list[str] | None = None
    if isinstance(tools_block, dict):
        raw_allow = tools_block.get("allow")
        if isinstance(raw_allow, list):
            tools_allow = [str(x) for x in raw_allow]

    # Flat ``tools_allow:`` (e.g. agents/demo-agent/agent.yaml); nested
    # ``tools.allow`` wins when both are present.
    if tools_allow is None:
        raw_flat = data.get("tools_allow")
        if isinstance(raw_flat, list):
            tools_allow = [str(x) for x in raw_flat if str(x).strip()]

    release_block = data.get("release") or {}
    release_config: dict[str, Any] | None = None
    if isinstance(release_block, dict) and release_block:
        release_config = {
            "strategy": release_block.get("strategy", "full"),
        }
        if "canary" in release_block:
            release_config["canary"] = release_block["canary"]
        if "pinned_version" in release_block:
            release_config["pinned_version"] = release_block["pinned_version"]

    row: dict[str, Any] = {
        "id": data["id"],
        "name": data["name"],
        "version": data["version"],
        "description": data.get("description"),
        "instruction": data.get("instruction"),
        "runspec_schema_version": int(data.get("runspec_schema_version", 1)),
        "owner": data.get("owner"),
        "lifecycle_state": data.get("lifecycle_state", "active"),
        "tags": data.get("tags"),
        "model_policy": data.get("model_policy"),
        "knowledge_scopes": data.get("knowledge_scopes"),
        "output_schema": data.get("output_schema"),
        "limits_config": data.get("limits"),
        "concurrency_config": data.get("concurrency"),
        "audit_config": data.get("audit"),
        "enterprise_config": data.get("enterprise"),
        "ui_config": data.get("ui_config"),
        "degradation_exempt": bool(data.get("degradation_exempt", False)),
        "release_config": release_config,
        "tools_allow": tools_allow,
        "skill_config": (
            {
                "id": skill_block.get("id"),
                "version_pin": skill_block.get("version_pin", "latest"),
            }
            if skill_block.get("id")
            else None
        ),
    }

    if row["skill_config"] is None:
        raise ValueError("skill.id is required")

    validate_agent_id(str(row["id"]))
    return row


def validate_required_agent_fields(row: dict[str, Any]) -> None:
    """Validate mandatory fields after normalization."""
    if not row.get("name"):
        raise ValueError("name is required")
    if not row.get("version"):
        raise ValueError("version is required")
