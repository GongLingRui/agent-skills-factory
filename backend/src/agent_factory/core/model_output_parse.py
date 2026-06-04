"""Extract JSON from raw model text (fences, reasoning tags; docs/08)."""

from __future__ import annotations

import json
import re
from typing import Any

# re-export for callers
__all__ = [
    "extract_json_object_from_text",
    "output_matches_json_constraint",
    "strip_model_reasoning_markup",
    "unwrap_markdown_json_fence",
]

# Common chain-of-thought / reasoning wrappers (strip before JSON parse & display)
_REASONING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<think\b[^>]*>[\s\S]*?</think>", re.IGNORECASE),
    re.compile(r"<thinking>[\s\S]*?</thinking>", re.IGNORECASE),
    re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE),
)


def strip_model_reasoning_markup(text: str) -> str:
    """Remove reasoning blocks so prose / JSON can be validated or shown."""
    t = text
    for pat in _REASONING_PATTERNS:
        t = pat.sub("", t)
    return t.strip()


def unwrap_markdown_json_fence(text: str) -> str:
    """Strip optional ```json ... ``` fence."""
    m = re.search(
        r"```(?:json)?\s*([\s\S]*?)```",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return text.strip()


def extract_json_object_from_text(text: str) -> dict[str, Any] | None:
    """Best-effort parse of a single JSON object from model output."""
    stripped = strip_model_reasoning_markup(text)
    t = stripped.strip()
    for candidate in (t, unwrap_markdown_json_fence(t)):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        frag = t[start : end + 1]
        try:
            obj = json.loads(frag)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return None


def output_matches_json_constraint(
    text: str,
    *,
    schema_name: str | None,
    agent_id: str | None = None,
    package_metadata: dict[str, Any] | None = None,
    repo_root: Any | None = None,
) -> bool | None:
    """Whether text satisfies JSON ``output_schema`` when ``schema_name`` is set.

    Uses jsonschema when a schema file is resolvable (docs/08); otherwise
    falls back to JSON object parseability.

    Returns:
        ``None`` if no schema (skip validation),
        ``True`` / ``False`` when validation applies.
    """
    if not schema_name:
        return None
    from agent_factory.core.output_schema_validator import (
        output_matches_schema_constraint,
    )

    validated = output_matches_schema_constraint(
        text,
        schema_name=schema_name,
        agent_id=agent_id,
        package_metadata=package_metadata,
        repo_root=repo_root,
    )
    if validated is not None:
        return validated
    stripped = strip_model_reasoning_markup(text)
    try:
        json.loads(stripped)
        return True
    except json.JSONDecodeError:
        pass
    if extract_json_object_from_text(text) is not None:
        return True
    return False
