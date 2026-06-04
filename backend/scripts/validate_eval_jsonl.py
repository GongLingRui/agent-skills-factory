#!/usr/bin/env python3
"""Validate evals/*.jsonl under the repo (docs/04). Exit 1 on format errors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agent_factory.core.eval_jsonl import validate_eval_case_dict


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    paths = sorted(
        p
        for p in repo_root.rglob("*.jsonl")
        if p.is_file() and p.parent.name == "evals"
    )
    if not paths:
        print("No evals/*.jsonl found; nothing to validate.")
        return 0

    errors: list[str] = []
    for path in paths:
        rel = path.relative_to(repo_root)
        text = path.read_text(encoding="utf-8")
        line_no = 0
        nonempty = 0
        for line in text.splitlines():
            line_no += 1
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            nonempty += 1
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"{rel}:{line_no}: invalid JSON: {exc}")
                continue
            for err in validate_eval_case_dict(obj):
                errors.append(f"{rel}:{line_no}: {err}")

        if nonempty == 0:
            errors.append(f"{rel}: no non-empty JSON lines")

    if errors:
        print("Eval JSONL validation failed:", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"Validated {len(paths)} evals file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
