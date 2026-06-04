"""SKILL.md YAML frontmatter parsing and validation (docs/04-skill-package-spec.md)."""

from __future__ import annotations

import re
from typing import Any

import yaml

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$")

_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n"
    r"(.*?)"
    r"^---[ \t]*\r?\n",
    re.DOTALL | re.MULTILINE,
)


def split_skill_md(content: str) -> tuple[dict[str, Any], str]:
    """Split SKILL.md into frontmatter dict and Markdown body.

    Args:
        content: Full SKILL.md text.

    Returns:
        Parsed frontmatter as a dict (may be empty if YAML is empty)
        and the body text after the closing ``---``.

    Raises:
        ValueError: If leading YAML frontmatter delimiters are missing or invalid.
    """
    text = content.lstrip("\ufeff")
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise ValueError(
            "SKILL.md must start with YAML frontmatter: opening ---, "
            "a YAML block, then a line containing only ---"
        )
    yaml_block = match.group(1)
    body = text[match.end() :]
    try:
        loaded = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in SKILL.md frontmatter: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")

    return loaded, body


def validate_skill_frontmatter(
    data: dict[str, Any],
    *,
    expected_name: str | None = None,
) -> None:
    """Validate required SKILL.md frontmatter fields per docs/04.

    Args:
        data: Parsed frontmatter mapping.
        expected_name: If set, ``name`` must match this skill id.

    Raises:
        ValueError: On validation failure.
    """
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            "frontmatter 'name' is required and must be a non-empty string"
        )

    name_key = name.strip()
    if not _NAME_PATTERN.match(name_key):
        raise ValueError(
            "frontmatter 'name' must be lowercase letters, digits, hyphens only "
            "(see docs/04-skill-package-spec.md)"
        )

    if expected_name is not None and name_key != expected_name:
        raise ValueError(
            f"frontmatter 'name' ({name_key!r}) must match skill id ({expected_name!r})"
        )

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(
            "frontmatter 'description' is required and must be a non-empty string"
        )

    when_to_use = data.get("when_to_use")
    if not isinstance(when_to_use, str) or not when_to_use.strip():
        raise ValueError(
            "frontmatter 'when_to_use' is required and must be a non-empty string"
        )
