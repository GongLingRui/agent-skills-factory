"""Controlled script execution: subprocess or gVisor (docs/25)."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from agent_factory.workers.gvisor_runner import (
    gvisor_available,
    run_controlled_script_gvisor,
)

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


def _run_subprocess_sandbox(
    *,
    script_source: str,
    hook_id: str,
    input_payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="af_script_") as tmp:
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
        env = {
            "PATH": "/usr/bin:/bin",
            "PYTHONNOUSERSITE": "1",
            "HOME": str(tdir),
        }
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(wrapper),
                    str(in_file),
                    str(script_file),
                    str(out_file),
                ],
                capture_output=True,
                text=True,
                timeout=max(1, timeout_seconds),
                cwd=str(tdir),
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"script timeout after {timeout_seconds}s") from exc
        if proc.returncode != 0:
            raise RuntimeError(
                (proc.stderr or proc.stdout or "script failed")[:2000]
            )
        if not out_file.is_file():
            raise RuntimeError("script produced no output file")
        data = json.loads(out_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("script output must be a JSON object")
        return data


def resolve_script_worker_runtime(
    configured: str,
    *,
    runsc_path: str = "",
) -> str:
    """``auto`` prefers gVisor when ``runsc`` is on PATH."""
    mode = (configured or "auto").strip().lower()
    if mode == "auto":
        return "gvisor" if gvisor_available(runsc_path) else "subprocess"
    if mode in ("gvisor", "subprocess"):
        return mode
    return "subprocess"


def run_controlled_script(
    *,
    script_source: str,
    hook_id: str,
    input_payload: dict[str, Any],
    timeout_seconds: int = 10,
    allow_network: bool = False,
    worker_runtime: str = "auto",
    runsc_path: str = "",
    gvisor_rootless: bool = True,
) -> dict[str, Any]:
    """Execute script; return structured output or raise ``RuntimeError``."""
    if allow_network:
        raise RuntimeError("network=true scripts are not permitted in this worker")
    mode = resolve_script_worker_runtime(worker_runtime, runsc_path=runsc_path)
    if mode == "gvisor":
        return run_controlled_script_gvisor(
            script_source=script_source,
            hook_id=hook_id,
            input_payload=input_payload,
            timeout_seconds=timeout_seconds,
            allow_network=allow_network,
            runsc_path=runsc_path,
            rootless=gvisor_rootless,
        )
    return _run_subprocess_sandbox(
        script_source=script_source,
        hook_id=hook_id,
        input_payload=input_payload,
        timeout_seconds=timeout_seconds,
    )
