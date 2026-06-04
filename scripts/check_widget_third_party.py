#!/usr/bin/env python3
"""Fail CI if Chat Widget declares known analytics / tracking SDKs (prd §10.7).

Scans ``frontend/package.json`` dependency keys (no network). Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_PACKAGE_JSON = _REPO / "frontend" / "package.json"

# Lowercase substring checks on "section:name@version" lines.
_FORBIDDEN = (
    "google-analytics",
    "googletagmanager",
    "/gtag",
    "react-ga",
    "@segment/",
    "segment/analytics",
    "mixpanel",
    "amplitude",
    "hotjar",
    "fullstory",
    "clarity-js",
    "facebook-pixel",
    "tiktok-pixel",
)


def main() -> int:
    if not _PACKAGE_JSON.is_file():
        print("skip: frontend/package.json missing", file=sys.stderr)
        return 0
    raw = json.loads(_PACKAGE_JSON.read_text(encoding="utf-8"))
    lines: list[str] = []
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        block = raw.get(section)
        if not isinstance(block, dict):
            continue
        for name, ver in block.items():
            lines.append(f"{section}:{str(name).lower()}@{str(ver).lower()}")
    blob = "\n".join(lines)
    hits = [s for s in _FORBIDDEN if s in blob]
    if hits:
        print(
            "Forbidden third-party analytics SDK tokens in package.json:",
            ", ".join(sorted(set(hits))),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
