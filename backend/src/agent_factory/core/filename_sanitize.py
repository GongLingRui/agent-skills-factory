"""Safe display/storage names for uploads (路径穿越 / 信息安全 §6.2 (5))."""

from __future__ import annotations

import re
import unicodedata


def sanitize_upload_filename(name: str | None, *, max_len: int = 200) -> str:
    """Return a single-segment safe filename for DB / logs (not storage path).

    - Drops directory components and NUL.
    - Removes ASCII control characters.
    - Replaces risky punctuation with ``_``; keeps letters, digits, ``.-_``,
      spaces, and common CJK ranges.
    """
    raw = (name or "").strip()
    if not raw:
        return "upload"
    # NUL before path parsing — avoids ``name\\x00/../../x`` selecting ``x``.
    raw = raw.split("\x00", 1)[0].strip()
    if not raw:
        return "upload"
    base = raw.replace("\\", "/").split("/")[-1]
    base = unicodedata.normalize("NFC", base)
    base = "".join(ch for ch in base if unicodedata.category(ch) != "Cc")
    base = base.strip(". ")
    if not base or base in (".", ".."):
        return "upload"
    safe = re.sub(
        r"[^\w\-. \u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]",
        "_",
        base,
        flags=re.UNICODE,
    )
    safe = re.sub(r"_+", "_", safe).strip("._ ") or "upload"
    if len(safe) > max_len:
        root, dot, ext = safe.rpartition(".")
        if dot and 1 <= len(ext) <= 10 and root:
            keep = max_len - len(ext) - 1
            safe = f"{root[: max(1, keep)]}.{ext}"
        else:
            safe = safe[:max_len]
    stem = safe.rsplit(".", 1)[0].upper() if "." in safe else safe.upper()
    if stem in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM0",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT0",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }:
        return f"_{safe}"
    return safe
