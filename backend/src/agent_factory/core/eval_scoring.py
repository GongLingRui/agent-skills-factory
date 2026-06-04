"""Score Skill eval cases from model text vs expectations (docs/04 §评测集)."""

from __future__ import annotations

from typing import Any

from agent_factory.core.model_output_parse import extract_json_object_from_text


def score_case_output(*, text: str, case: dict[str, Any]) -> tuple[float, list[str]]:
    """Compute a 0..1 score and human-readable reasons.

    Rules (aligned with docs/04):
    - ``expected_schema_fields``: all keys must exist in parsed JSON object.
    - ``expected_tags``: each tag should appear in output (case-insensitive).
    - If both are set, the score is the minimum of the two partial scores
      (both must pass for high scores).
    - If neither is set, non-empty output scores 1.0 (smoke pass).

    Args:
        text: Full model output text.
        case: One eval case dict (same object shape as JSONL line).

    Returns:
        (score, reasons) where reasons explain failures for operators.
    """
    reasons: list[str] = []
    tags = case.get("expected_tags")
    fields = case.get("expected_schema_fields")

    has_tags = isinstance(tags, list) and len(tags) > 0
    has_fields = isinstance(fields, list) and len(fields) > 0

    if not has_tags and not has_fields:
        if text.strip():
            return 1.0, []
        return 0.0, ["empty model output"]

    scores: list[float] = []

    if has_fields:
        assert isinstance(fields, list)
        obj = extract_json_object_from_text(text)
        if obj is None:
            scores.append(0.0)
            reasons.append("could not parse JSON object for schema check")
        else:
            missing = [f for f in fields if f not in obj]
            if missing:
                scores.append(0.0)
                reasons.append(f"missing schema fields: {', '.join(missing)}")
            else:
                scores.append(1.0)

    if has_tags:
        assert isinstance(tags, list)
        lower = text.lower()
        missing_t = [str(t) for t in tags if str(t).lower() not in lower]
        if missing_t:
            scores.append(0.0)
            reasons.append(f"missing expected_tags: {', '.join(missing_t)}")
        else:
            scores.append(1.0)

    if not scores:
        return 1.0, []

    return float(min(scores)), reasons
