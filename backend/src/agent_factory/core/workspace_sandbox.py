"""Workspace path sandbox for fs.* / shell.exec tools (OpenClaw-style agents)."""

from __future__ import annotations

from pathlib import Path

from agent_factory.config import Settings, get_settings
from agent_factory.middleware.error_handler import AgentFactoryException


def workspace_root(settings: Settings | None = None) -> Path:
    """Return configured workspace root (must exist)."""
    cfg = settings or get_settings()
    raw = (cfg.WORKSPACE_ROOT or "").strip()
    if raw:
        root = Path(raw).expanduser()
    else:
        # backend/src/agent_factory/core -> repo root
        root = Path(__file__).resolve().parents[4]
    resolved = root.resolve()
    if not resolved.is_dir():
        raise AgentFactoryException(
            "WORKSPACE_UNAVAILABLE",
            f"Workspace root is not a directory: {resolved}",
            status_code=503,
        )
    return resolved


def resolve_workspace_path(
    raw_path: str,
    *,
    settings: Settings | None = None,
    must_exist: bool = False,
) -> Path:
    """Resolve *raw_path* under workspace root; reject path traversal."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "file_path (or path) is required",
            status_code=400,
        )
    root = workspace_root(settings)
    candidate = Path(raw_path.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=must_exist)
    except FileNotFoundError as exc:
        raise AgentFactoryException(
            "NOT_FOUND",
            f"Path not found: {raw_path}",
            status_code=404,
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise AgentFactoryException(
            "FORBIDDEN",
            "Path escapes workspace sandbox",
            status_code=403,
        ) from exc
    return resolved
