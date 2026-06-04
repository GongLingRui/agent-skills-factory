"""User text normalization (信息安全 §5.5.2 对抗样本 / 隐形字符)."""

from __future__ import annotations

import unicodedata


def strip_format_and_control_chars(text: str, *, max_chars: int) -> str:
    """NFKC + drop format/control codepoints; cap length.

    Removes Unicode category ``Cf`` (format, incl. ZWJ abuse helpers),
    ``Cc`` (C0/C1 controls), and bidi override characters often used to
    obfuscate malicious instructions.
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text)
    out: list[str] = []
    for ch in s:
        cat = unicodedata.category(ch)
        o = ord(ch)
        if cat in ("Cf", "Cc", "Cs"):
            continue
        if o in range(0x202A, 0x202F) or o in range(0x2066, 0x206A):
            continue
        if o in (0xFEFF, 0x200B, 0x200C, 0x200D, 0x2060):
            continue
        out.append(ch)
        if len(out) >= max_chars:
            break
    return "".join(out)
