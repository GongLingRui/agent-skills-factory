"""gVisor (runsc) sandbox for controlled scripts (docs/25)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_RUNNER_WRAPPER = textwrap.dedent(
    '''
    import json, sys
    from pathlib import Path

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    script_path = Path(sys.argv[2])
    ns = {"__name__": "__main__", "input": payload.get("input", {})}
    code = script_path.read_text(encoding="utf-8")
    exec(compile(code, str(script_path), "exec"), ns)
    out = ns.get("output", ns.get("result", {}))
    if not isinstance(out, dict):
        out = {"result": out}
    Path(sys.argv[3]).write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8"
    )
    '''
)


def resolve_runsc_binary(explicit_path: str = "") -> str | None:
    """Return ``runsc`` path if installed."""
    if explicit_path.strip():
        p = Path(explicit_path.strip())
        if p.is_file():
            return str(p)
    found = shutil.which("runsc")
    return found


def gvisor_available(explicit_path: str = "") -> bool:
    return resolve_runsc_binary(explicit_path) is not None


def run_controlled_script_gvisor(
    *,
    script_source: str,
    hook_id: str,
    input_payload: dict[str, Any],
    timeout_seconds: int = 10,
    allow_network: bool = False,
    runsc_path: str = "",
    rootless: bool = True,
) -> dict[str, Any]:
    """Execute via ``runsc do`` (network isolated by default)."""
    if allow_network:
        raise RuntimeError("network=true scripts are not permitted in gVisor worker")
    runsc = resolve_runsc_binary(runsc_path)
    if not runsc:
        raise RuntimeError("runsc binary not found (install gVisor or set SCRIPT_GVISOR_RUNSC)")

    with tempfile.TemporaryDirectory(prefix="af_gvisor_") as tmp:
        tdir = Path(tmp)
        script_file = tdir / "user_script.py"
        script_file.write_text(script_source, encoding="utf-8")
        in_file = tdir / "in.json"
        out_file = tdir / "out.json"
        in_file.write_text(
            json.dumps({"hook_id": hook_id, "input": input_payload}),
            encoding="utf-8",
        )
        wrapper = tdir / "wrapper.py"
        wrapper.write_text(_RUNNER_WRAPPER, encoding="utf-8")
        cmd: list[str] = [runsc]
        if rootless:
            cmd.append("--rootless")
        cmd.extend(["do", "--network=none", "--"])
        cmd.extend(
            [
                sys.executable,
                str(wrapper),
                str(in_file),
                str(script_file),
                str(out_file),
            ]
        )
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(1, timeout_seconds),
                cwd=str(tdir),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"gVisor script timeout after {timeout_seconds}s") from exc
        if proc.returncode != 0:
            logger.warning(
                "gVisor runsc stderr: %s",
                (proc.stderr or "")[:1000],
            )
            raise RuntimeError(
                (proc.stderr or proc.stdout or "gVisor script failed")[:2000]
            )
        if not out_file.is_file():
            raise RuntimeError("gVisor script produced no output file")
        data = json.loads(out_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("script output must be a JSON object")
        return data
