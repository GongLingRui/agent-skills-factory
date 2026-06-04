"""OpenClaw shell.process tool — background process management."""

from __future__ import annotations

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent_factory.config import Settings, get_settings
from agent_factory.core.workspace_sandbox import resolve_workspace_path, workspace_root
from agent_factory.middleware.error_handler import AgentFactoryException

PROCESS_TOOL_IDS: frozenset[str] = frozenset({"shell.process"})

_PROCESS_ACTIONS = frozenset(
    {"list", "poll", "log", "write", "send-keys", "submit", "paste", "kill", "clear", "remove"}
)


@dataclass
class BackgroundProcess:
    process_id: str
    command: str
    popen: subprocess.Popen[str]
    cwd: str
    created_at: float = field(default_factory=time.time)
    log_lines: list[str] = field(default_factory=list)
    stdin_buffer: str = ""


class ProcessRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: dict[str, BackgroundProcess] = {}

    def spawn(self, command: str, *, cwd: str) -> BackgroundProcess:
        pid = f"proc_{uuid.uuid4().hex[:10]}"
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        bg = BackgroundProcess(process_id=pid, command=command, popen=proc, cwd=cwd)
        with self._lock:
            self._processes[pid] = bg
        threading.Thread(target=self._drain, args=(bg,), daemon=True).start()
        return bg

    def _drain(self, bg: BackgroundProcess) -> None:
        if bg.popen.stdout is None:
            return
        for line in bg.popen.stdout:
            with self._lock:
                bg.log_lines.append(line.rstrip("\n"))
                if len(bg.log_lines) > 5000:
                    bg.log_lines = bg.log_lines[-4000:]

    def get(self, process_id: str) -> BackgroundProcess | None:
        with self._lock:
            return self._processes.get(process_id)

    def list_all(self) -> list[BackgroundProcess]:
        with self._lock:
            return list(self._processes.values())

    def remove(self, process_id: str) -> bool:
        with self._lock:
            return self._processes.pop(process_id, None) is not None


_REGISTRY = ProcessRegistry()


def handle_shell_process(params: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    if not cfg.WORKSPACE_TOOLS_ENABLED:
        raise AgentFactoryException(
            "WORKSPACE_DISABLED",
            "shell.process requires workspace tools",
            status_code=503,
        )
    action = str(params.get("action") or "list").strip().lower()
    if action not in _PROCESS_ACTIONS:
        raise AgentFactoryException(
            "INVALID_PARAMS", f"Unknown process action: {action}", status_code=400
        )

    if action == "list":
        rows = []
        for p in _REGISTRY.list_all():
            rc = p.popen.poll()
            rows.append(
                {
                    "processId": p.process_id,
                    "command": p.command,
                    "cwd": p.cwd,
                    "running": rc is None,
                    "exitCode": rc,
                    "logLines": len(p.log_lines),
                }
            )
        return {"processes": rows, "total": len(rows)}

    process_id = str(params.get("processId") or params.get("process_id") or "").strip()
    if action == "submit" or (action == "poll" and not process_id):
        command = str(params.get("command") or "").strip()
        if not command:
            raise AgentFactoryException(
                "INVALID_PARAMS", "command required for submit", status_code=400
            )
        cwd_raw = params.get("cwd")
        cwd = (
            str(resolve_workspace_path(str(cwd_raw), settings=cfg, must_exist=True))
            if cwd_raw
            else str(workspace_root(cfg))
        )
        bg = _REGISTRY.spawn(command, cwd=cwd)
        return {"processId": bg.process_id, "status": "started", "command": command}

    if not process_id:
        raise AgentFactoryException(
            "INVALID_PARAMS", "processId required", status_code=400
        )
    bg = _REGISTRY.get(process_id)
    if bg is None:
        raise AgentFactoryException(
            "NOT_FOUND", f"Process not found: {process_id}", status_code=404
        )

    if action == "poll":
        rc = bg.popen.poll()
        return {
            "processId": process_id,
            "running": rc is None,
            "exitCode": rc,
        }

    if action == "log":
        tail = int(params.get("tail") or 200)
        lines = bg.log_lines[-tail:]
        return {"processId": process_id, "lines": lines, "total": len(lines)}

    if action in ("write", "send-keys", "paste"):
        text = str(params.get("text") or params.get("input") or "")
        if bg.popen.stdin is None and bg.popen.poll() is None:
            try:
                if bg.popen.stdin:
                    bg.popen.stdin.write(text)
                    bg.popen.stdin.flush()
            except Exception:
                bg.stdin_buffer += text
        else:
            bg.stdin_buffer += text
        return {"processId": process_id, "written": len(text)}

    if action == "kill":
        bg.popen.kill()
        return {"processId": process_id, "status": "killed"}

    if action == "clear":
        bg.log_lines.clear()
        return {"processId": process_id, "status": "cleared"}

    if action == "remove":
        if bg.popen.poll() is None:
            bg.popen.kill()
        _REGISTRY.remove(process_id)
        return {"processId": process_id, "status": "removed"}

    raise AgentFactoryException("INVALID_PARAMS", f"Unhandled action {action}", status_code=400)
