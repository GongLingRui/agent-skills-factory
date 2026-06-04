#!/usr/bin/env python3
"""P0 自动化门禁：ruff + pytest（对齐 docs/34、plan §4.10）。

用法（在 backend/ 目录）::

    uv run python scripts/verify_p0.py

退出码：0 成功，非 0 失败。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(argv: list[str], cwd: Path) -> int:
    print("+", " ".join(argv), flush=True)
    return subprocess.call(argv, cwd=str(cwd))


def main() -> int:
    parser = argparse.ArgumentParser(description="P0 verify: ruff + pytest")
    parser.add_argument(
        "--skip-ruff",
        action="store_true",
        help="only run pytest",
    )
    args = parser.parse_args()

    backend = Path(__file__).resolve().parent.parent
    if not (backend / "pyproject.toml").exists():
        print(
            "ERROR: run from repo layout with backend/pyproject.toml",
            file=sys.stderr,
        )
        return 2

    if not args.skip_ruff:
        rc = _run(
            ["uv", "run", "ruff", "check", "src", "tests", "scripts"],
            backend,
        )
        if rc != 0:
            return rc

    rc = _run(["uv", "run", "pytest", "tests/", "-q", "--tb=short"], backend)
    if rc != 0:
        return rc

    print(
        "\nP0 automated gate passed.\n"
        "Manual / environment still required: portal→widget E2E, staging smoke, "
        "security review — see docs/34-p0-delivery-spec.md checklist.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
