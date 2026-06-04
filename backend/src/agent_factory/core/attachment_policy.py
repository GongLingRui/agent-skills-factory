"""Upload constraints from Agent ``ui_config.attachments`` (docs/39)."""

from __future__ import annotations

import fnmatch
from typing import Any

DEFAULT_MAX_BYTES = 10 * 1024 * 1024

# First chunk used for magic-byte sniffing (plan §12 hardening).
MAGIC_SNIFF_BYTES = 512

_OOXML_DOCX = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_OOXML_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_OOXML_PPTX = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)

_ZIP_FAMILY = frozenset(
    {
        "application/zip",
        _OOXML_DOCX,
        _OOXML_XLSX,
        _OOXML_PPTX,
    }
)


def _attachments_section(ui_config: dict[str, Any] | None) -> dict[str, Any]:
    if not ui_config:
        return {}
    raw = ui_config.get("attachments")
    return raw if isinstance(raw, dict) else {}


def _max_bytes(section: dict[str, Any]) -> int:
    mb = section.get("max_size_mb")
    if isinstance(mb, (int, float)) and mb > 0:
        return int(mb * 1024 * 1024)
    return DEFAULT_MAX_BYTES


def sniff_mime_magic(head: bytes) -> str | None:
    """Best-effort MIME from leading bytes; ``None`` if unknown or too short."""
    if len(head) < 4:
        return None
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if (
        len(head) >= 12
        and head.startswith(b"RIFF")
        and head[8:12] == b"WEBP"
    ):
        return "image/webp"
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"
    if head.startswith(b"MZ"):
        return "application/x-msdownload"
    return None


def _mime_compatible(declared: str, sniffed: str) -> bool:
    d, s = declared.lower(), sniffed.lower()
    if d == s:
        return True
    if d in _ZIP_FAMILY and s in _ZIP_FAMILY:
        return True
    if d in ("image/jpg", "image/jpeg") and s in ("image/jpg", "image/jpeg"):
        return True
    return False


def _executable_disguise(filename: str, sniffed: str | None) -> bool:
    """True when PE executable magic but filename hides as document/image."""
    if sniffed != "application/x-msdownload":
        return False
    low = filename.lower()
    safe_suffix = (".exe", ".msi", ".dll", ".bat", ".cmd", ".scr")
    return not any(low.endswith(x) for x in safe_suffix)


def _extension_magic_consistent(filename: str, sniffed: str | None) -> bool:
    """Reject obvious extension lies when magic is confident."""
    if not sniffed:
        return True
    low = filename.lower()
    if low.endswith(".pdf"):
        return sniffed == "application/pdf"
    if low.endswith(".png"):
        return sniffed == "image/png"
    if low.endswith((".jpg", ".jpeg")):
        return sniffed == "image/jpeg"
    if low.endswith(".gif"):
        return sniffed == "image/gif"
    if low.endswith(".webp"):
        return sniffed == "image/webp"
    if low.endswith(".docx"):
        return sniffed in _ZIP_FAMILY
    if low.endswith(".xlsx"):
        return sniffed in _ZIP_FAMILY
    if low.endswith(".pptx"):
        return sniffed in _ZIP_FAMILY
    return True


def _matches_pattern(filename: str, mime_type: str, pattern: str) -> bool:
    p = pattern.strip()
    if not p:
        return False
    low = p.lower()
    if low.startswith("."):
        return filename.lower().endswith(low)
    if "*" in p or "?" in p:
        return fnmatch.fnmatch(mime_type.lower(), low)
    return mime_type.lower() == low


def validate_upload_for_ui_config(
    *,
    filename: str,
    mime_type: str,
    size_bytes: int,
    ui_config: dict[str, Any] | None,
    content_head: bytes | None = None,
) -> tuple[bool, str | None]:
    """Return (ok, error_code). ``error_code`` maps to API ``AgentFactoryException``.

    When ``content_head`` is set (typically first :data:`MAGIC_SNIFF_BYTES` bytes),
    declared MIME is cross-checked with magic bytes to reduce spoofing.
    """
    section = _attachments_section(ui_config)
    if section.get("enabled") is False:
        return False, "ATTACHMENTS_DISABLED"

    max_b = _max_bytes(section)
    if size_bytes > max_b:
        return False, "FILE_TOO_LARGE"

    declared_raw = (mime_type or "").strip().lower()
    declared = declared_raw or "application/octet-stream"
    sniffed: str | None = None
    if content_head:
        sniffed = sniff_mime_magic(content_head[:MAGIC_SNIFF_BYTES])

    effective_mime = declared
    if sniffed:
        if _executable_disguise(filename, sniffed):
            return False, "MIME_MAGIC_MISMATCH"
        if not _extension_magic_consistent(filename, sniffed):
            return False, "MIME_MAGIC_MISMATCH"
        if declared in ("application/octet-stream", "binary/octet-stream", ""):
            effective_mime = sniffed
        elif not _mime_compatible(declared, sniffed):
            return False, "MIME_MAGIC_MISMATCH"

    accept = section.get("accept")
    if isinstance(accept, list) and accept:
        patterns = [str(x).strip() for x in accept if str(x).strip()]
        if patterns:
            if not any(
                _matches_pattern(filename, effective_mime, pat) for pat in patterns
            ):
                return False, "FILE_TYPE_NOT_ALLOWED"

    return True, None
