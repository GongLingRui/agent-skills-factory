"""OpenClaw code_execution tool — sandboxed Python execution."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from agent_factory.config import Settings, get_settings
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.workers.gvisor_runner import gvisor_available, run_controlled_script_gvisor

CODE_EXECUTION_TOOL_IDS: frozenset[str] = frozenset({"runtime.code_execution"})


def handle_code_execution(params: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    if not cfg.CODE_EXECUTION_ENABLED:
        raise AgentFactoryException(
            "CODE_EXEC_DISABLED",
            "code_execution disabled (set CODE_EXECUTION_ENABLED=true)",
            status_code=503,
        )
    task = str(params.get("task") or params.get("code") or "").strip()
    if not task:
        raise AgentFactoryException(
            "INVALID_PARAMS", "task is required", status_code=400
        )
    timeout = int(params.get("timeoutSeconds") or params.get("timeout_seconds") or 30)
    timeout = max(5, min(timeout, int(cfg.CODE_EXECUTION_TIMEOUT_SECONDS)))

    import json

    script = textwrap.dedent(
        f"""
        import json, sys
        CODE = {json.dumps(task)}
        g = {{"__name__": "__main__", "task": CODE}}
        exec(compile(CODE, "<code_execution>", "exec"), g)
        """
    ).strip()

    if cfg.CODE_EXECUTION_USE_GVISOR and gvisor_available(cfg.SCRIPT_GVISOR_RUNSC):
        try:
            out = run_controlled_script_gvisor(
                script_source=script,
                hook_id="code_execution",
                input_payload={"task": task},
                timeout_seconds=timeout,
                runsc_path=cfg.SCRIPT_GVISOR_RUNSC,
            )
            return {"status": "ok", "runtime": "gvisor", "output": out}
        except Exception as exc:
            raise AgentFactoryException(
                "EXEC_FAILED", str(exc), status_code=500
            ) from exc

    with tempfile.TemporaryDirectory(prefix="af_code_exec_") as tmp:
        script_path = Path(tmp) / "task.py"
        script_path.write_text(script, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp,
            )
        except subprocess.TimeoutExpired as exc:
            raise AgentFactoryException(
                "TIMEOUT", f"Execution timed out after {timeout}s", status_code=408
            ) from exc

    stdout = (proc.stdout or "")[: cfg.CODE_EXECUTION_MAX_OUTPUT_CHARS]
    stderr = (proc.stderr or "")[: cfg.CODE_EXECUTION_MAX_OUTPUT_CHARS]
    if proc.returncode != 0:
        raise AgentFactoryException(
            "EXEC_FAILED",
            stderr or stdout or f"exit code {proc.returncode}",
            status_code=500,
        )
    return {
        "status": "ok",
        "runtime": "subprocess",
        "stdout": stdout,
        "stderr": stderr,
        "exitCode": proc.returncode,
    }
