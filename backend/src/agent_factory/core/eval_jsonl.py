"""Validate ``evals/skill_cases.jsonl`` case objects (docs/04-skill-package-spec)."""

from __future__ import annotations

from typing import Any


def validate_eval_case_dict(obj: Any) -> list[str]:
    """Check one case line (parsed JSON). Return human-readable errors; empty if ok.

    Required per docs/04: ``id``, ``name``, ``input.message``, ``min_score`` in 0..1.
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["case must be a JSON object"]

    cid = obj.get("id")
    if not isinstance(cid, str) or not cid.strip():
        errors.append("missing or invalid string field: id")

    name = obj.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("missing or invalid string field: name")

    inp = obj.get("input")
    if not isinstance(inp, dict):
        errors.append("missing or invalid object field: input")
    else:
        msg = inp.get("message")
        if not isinstance(msg, str) or not msg.strip():
            errors.append("input.message must be a non-empty string")

    score = obj.get("min_score")
    if not isinstance(score, (int, float)):
        errors.append("min_score must be a number")
    else:
        s = float(score)
        if s < 0.0 or s > 1.0:
            errors.append("min_score must be between 0 and 1")

    return errors
