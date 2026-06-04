"""scripts/check_widget_third_party.py (prd §10.7)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "check_widget_third_party.py"


def test_widget_third_party_script_exits_zero_on_repo_package_json() -> None:
    assert _SCRIPT.is_file(), _SCRIPT
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
