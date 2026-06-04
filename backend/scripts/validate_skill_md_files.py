#!/usr/bin/env python3
"""Validate all SKILL.md files under the repository root (docs/04).

Exit 0 when no files or all valid; exit 1 on validation errors.
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_factory.core.skill_frontmatter import (
    split_skill_md,
    validate_skill_frontmatter,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    paths = sorted(repo_root.rglob("SKILL.md"))
    if not paths:
        print("No SKILL.md files found; nothing to validate.")
        return 0

    errors: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        try:
            fm, _body = split_skill_md(text)
            validate_skill_frontmatter(fm)
        except ValueError as exc:
            rel = path.relative_to(repo_root)
            errors.append(f"{rel}: {exc}")

    if errors:
        print("SKILL.md validation failed:", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"Validated {len(paths)} SKILL.md file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
