"""Lightweight prompt-injection heuristics (docs/34)."""

from __future__ import annotations

import re

_HIGH_RISK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.I),
    re.compile(r"disregard\s+(the\s+)?(above|system)", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"<\s*/\s*system\s*>", re.I),
)


def prompt_injection_risk_score(text: str) -> int:
    """Return 0 (none) or higher when heuristics fire."""
    if not text or len(text) < 8:
        return 0
    score = 0
    for pat in _HIGH_RISK_PATTERNS:
        if pat.search(text):
            score += 2
    if score > 8:
        score = 8
    return score
