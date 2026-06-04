"""Best-effort redaction of model output (信息安全 §5.2.3)."""

from __future__ import annotations

import re

# OpenAI-style secret key prefix (common accidental paste).
_SK_RE = re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")
# Long bearer-like tokens in prose.
_BEARER_RE = re.compile(
    r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*[A-Za-z0-9\-._~+/]{24,}\b",
    flags=re.IGNORECASE,
)
# AWS-ish access key id (20 uppercase alnum).
_AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")


def redact_sensitive_snippets(text: str) -> str:
    """Mask likely API keys / bearer tokens in assistant-visible text."""
    if not text:
        return text
    s = _SK_RE.sub("[REDACTED_SECRET]", text)
    s = _BEARER_RE.sub("Bearer [REDACTED]", s)
    s = _AWS_KEY_RE.sub("[REDACTED_AWS_KEY]", s)
    return s
