"""Tests for SKILL.md frontmatter helpers."""

import pytest

from agent_factory.core.skill_frontmatter import (
    split_skill_md,
    validate_skill_frontmatter,
)


def test_split_skill_md_ok():
    raw = """---
name: clause-review
description: Does things well.
when_to_use: When needed.
---

# Title

Body here.
"""
    fm, body = split_skill_md(raw)
    assert fm["name"] == "clause-review"
    assert body.lstrip().startswith("# Title")


def test_split_skill_md_no_opening():
    with pytest.raises(ValueError, match="YAML frontmatter"):
        split_skill_md("# No frontmatter\n")


def test_validate_skill_frontmatter_ok():
    validate_skill_frontmatter(
        {
            "name": "my-skill",
            "description": "Short description for discovery.",
            "when_to_use": "When user asks.",
        }
    )


def test_validate_invalid_name():
    with pytest.raises(ValueError, match="name"):
        validate_skill_frontmatter(
            {
                "name": "Bad_Name",
                "description": "x",
                "when_to_use": "y",
            }
        )


def test_validate_expected_name_mismatch():
    with pytest.raises(ValueError, match="must match"):
        validate_skill_frontmatter(
            {
                "name": "a",
                "description": "d",
                "when_to_use": "w",
            },
            expected_name="b",
        )
