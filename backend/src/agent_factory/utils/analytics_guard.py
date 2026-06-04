"""PII guard for analytics / transcript payloads.

Forces callers to explicitly declare that a string has been reviewed for
sensitive code snippets or file paths before it is written to analytics.
"""

from __future__ import annotations

import logging
import re
from typing import NewType

logger = logging.getLogger(__name__)

AnalyticsSafeString = NewType("AnalyticsSafeString", str)

# Basic path-like patterns (Windows + Unix)
_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|/)(?:[\w._-]+[\\/])*[\w._-]+",
    re.MULTILINE,
)
# Simple email-ish pattern
_EMAIL_RE = re.compile(r"[\w.-]+@[\w.-]+\.[A-Za-z]{2,}")


def sanitize_for_analytics(text: str) -> AnalyticsSafeString:
    """Best-effort redaction of paths and emails from *text*.

    Returns an ``AnalyticsSafeString`` so downstream callers must
    explicitly accept the sanitized value.
    """
    if not isinstance(text, str):
        text = str(text)
    # Redact paths
    out = _PATH_RE.sub("[REDACTED_PATH]", text)
    # Redact emails
    out = _EMAIL_RE.sub("[REDACTED_EMAIL]", out)
    return AnalyticsSafeString(out)
