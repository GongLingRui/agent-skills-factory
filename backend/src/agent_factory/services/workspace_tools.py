"""Built-in workspace tools (Read/Write/Edit/Glob/Grep/Bash/WebFetch parity)."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx

from agent_factory.config import Settings, get_settings
from agent_factory.core.workspace_sandbox import resolve_workspace_path, workspace_root
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.baidu_web_search_client import post_baidu_web_search

logger = logging.getLogger(__name__)

# Tool ids registered in ToolGateway (Claude Code / OpenClaw-style surface).
WORKSPACE_TOOL_IDS: frozenset[str] = frozenset(
    {
        "fs.read",
        "fs.write",
        "fs.edit",
        "fs.apply_patch",
        "fs.glob",
        "fs.grep",
        "shell.exec",
        "web.fetch",
        "web.search",
    }
)

READ_ONLY_WORKSPACE_TOOLS: frozenset[str] = frozenset(
    {"fs.read", "fs.glob", "fs.grep", "web.fetch", "web.search"}
)


def _require_workspace_enabled(settings: Settings) -> None:
    if not settings.WORKSPACE_TOOLS_ENABLED:
        raise AgentFactoryException(
            "WORKSPACE_DISABLED",
            "Workspace tools are disabled (set WORKSPACE_TOOLS_ENABLED=true)",
            status_code=503,
        )


def handle_fs_read(params: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    _require_workspace_enabled(settings or get_settings())
    cfg = settings or get_settings()
    path = resolve_workspace_path(str(params["file_path"]), settings=cfg, must_exist=True)
    if not path.is_file():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "file_path must be a regular file",
            status_code=400,
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    offset = int(params.get("offset") or 1)
    limit = params.get("limit")
    if offset < 1:
        offset = 1
    start = offset - 1
    if limit is not None:
        end = start + max(0, int(limit))
        chunk_lines = lines[start:end]
    else:
        chunk_lines = lines[start:]
    body = "".join(chunk_lines)
    max_chars = int(cfg.WORKSPACE_READ_MAX_CHARS)
    if len(body) > max_chars:
        body = body[:max_chars] + "\n…(truncated)"
    return {
        "file_path": str(path),
        "offset": offset,
        "limit": limit,
        "total_lines": len(lines),
        "content": body,
    }


def handle_fs_write(params: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    _require_workspace_enabled(settings or get_settings())
    cfg = settings or get_settings()
    content = params.get("content")
    if not isinstance(content, str):
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "content must be a string",
            status_code=400,
        )
    path = resolve_workspace_path(str(params["file_path"]), settings=cfg, must_exist=False)
    if path.exists() and path.is_dir():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "file_path must not be a directory",
            status_code=400,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    created = not path.exists()
    path.write_text(content, encoding="utf-8")
    return {
        "file_path": str(path),
        "bytes_written": len(content.encode("utf-8")),
        "created": created,
    }


def handle_fs_edit(params: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    _require_workspace_enabled(settings or get_settings())
    cfg = settings or get_settings()
    old = params.get("old_string")
    new = params.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str):
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "old_string and new_string must be strings",
            status_code=400,
        )
    if old == new:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "old_string and new_string must differ",
            status_code=400,
        )
    path = resolve_workspace_path(str(params["file_path"]), settings=cfg, must_exist=True)
    if not path.is_file():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "file_path must be a regular file",
            status_code=400,
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    replace_all = bool(params.get("replace_all", False))
    if replace_all:
        count = text.count(old)
        if count == 0:
            raise AgentFactoryException(
                "NOT_FOUND",
                "old_string not found in file",
                status_code=404,
            )
        updated = text.replace(old, new)
    else:
        if text.count(old) > 1:
            raise AgentFactoryException(
                "INVALID_PARAMS",
                "old_string is not unique; set replace_all=true or provide more context",
                status_code=400,
            )
        if old not in text:
            raise AgentFactoryException(
                "NOT_FOUND",
                "old_string not found in file",
                status_code=404,
            )
        updated = text.replace(old, new, 1)
        count = 1
    path.write_text(updated, encoding="utf-8")
    return {"file_path": str(path), "replacements": count}


def handle_fs_apply_patch(
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _require_workspace_enabled(settings or get_settings())
    cfg = settings or get_settings()
    patch = params.get("patch")
    if not isinstance(patch, str) or not patch.strip():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "patch must be a non-empty unified diff string",
            status_code=400,
        )
    path = resolve_workspace_path(str(params["file_path"]), settings=cfg, must_exist=True)
    if not path.is_file():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "file_path must be a regular file",
            status_code=400,
        )
    try:
        proc = subprocess.run(
            ["patch", str(path), "-p0"],
            input=patch,
            capture_output=True,
            text=True,
            timeout=float(cfg.SHELL_EXEC_TIMEOUT_SECONDS),
            cwd=str(path.parent),
        )
    except FileNotFoundError as exc:
        raise AgentFactoryException(
            "PATCH_UNAVAILABLE",
            "系统未安装 patch 命令，请改用 fs.edit",
            status_code=503,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AgentFactoryException("TIMEOUT", "patch timed out", status_code=408) from exc
    if proc.returncode != 0:
        raise AgentFactoryException(
            "PATCH_FAILED",
            (proc.stderr or proc.stdout or "patch failed")[:500],
            status_code=400,
        )
    return {"file_path": str(path), "applied": True}


def handle_fs_glob(params: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    _require_workspace_enabled(settings or get_settings())
    cfg = settings or get_settings()
    pattern = str(params.get("pattern") or "").strip()
    if not pattern:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "pattern is required",
            status_code=400,
        )
    base_raw = params.get("path")
    if base_raw:
        base = resolve_workspace_path(str(base_raw), settings=cfg, must_exist=True)
        if not base.is_dir():
            raise AgentFactoryException(
                "INVALID_PARAMS",
                "path must be a directory",
                status_code=400,
            )
    else:
        base = workspace_root(cfg)
    matches: list[str] = []
    max_results = int(cfg.WORKSPACE_GLOB_MAX_RESULTS)
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base).as_posix()
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(p.name, pattern):
            matches.append(str(p))
            if len(matches) >= max_results:
                break
    return {"pattern": pattern, "base": str(base), "matches": matches, "truncated": len(matches) >= max_results}


def _grep_with_rg(
    *,
    pattern: str,
    base: Path,
    glob_pat: str | None,
    head_limit: int,
) -> list[dict[str, Any]] | None:
    rg = shutil.which("rg")
    if not rg:
        return None
    cmd = [rg, "--json", "-e", pattern, str(base)]
    if glob_pat:
        cmd.extend(["--glob", glob_pat])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode not in (0, 1):
        return None
    out: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        if len(out) >= head_limit:
            break
        try:
            import json

            row = json.loads(line)
        except Exception:
            continue
        if row.get("type") != "match":
            continue
        data = row.get("data") or {}
        path_obj = data.get("path") or {}
        out.append(
            {
                "file": path_obj.get("text", ""),
                "line_number": (data.get("line_number") or 0),
                "line": ((data.get("lines") or {}).get("text") or "").rstrip("\n"),
            }
        )
    return out


def _grep_python_fallback(
    *,
    pattern: str,
    base: Path,
    glob_pat: str | None,
    head_limit: int,
    ignore_case: bool,
) -> list[dict[str, Any]]:
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            f"Invalid regex pattern: {exc}",
            status_code=400,
        ) from exc
    out: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        if glob_pat and not fnmatch.fnmatch(rel, glob_pat):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                out.append({"file": str(path), "line_number": i, "line": line})
                if len(out) >= head_limit:
                    return out
    return out


def handle_fs_grep(params: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    _require_workspace_enabled(settings or get_settings())
    cfg = settings or get_settings()
    pattern = str(params.get("pattern") or "").strip()
    if not pattern:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "pattern is required",
            status_code=400,
        )
    base_raw = params.get("path")
    if base_raw:
        base = resolve_workspace_path(str(base_raw), settings=cfg, must_exist=True)
    else:
        base = workspace_root(cfg)
    if not base.is_dir():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "path must be a directory",
            status_code=400,
        )
    glob_pat = params.get("glob")
    glob_str = str(glob_pat).strip() if isinstance(glob_pat, str) and glob_pat.strip() else None
    head_limit = int(params.get("head_limit") or cfg.WORKSPACE_GREP_MAX_RESULTS)
    ignore_case = bool(params.get("-i") or params.get("ignore_case"))
    matches = _grep_with_rg(
        pattern=pattern,
        base=base,
        glob_pat=glob_str,
        head_limit=head_limit,
    )
    engine = "rg"
    if matches is None:
        engine = "python"
        matches = _grep_python_fallback(
            pattern=pattern,
            base=base,
            glob_pat=glob_str,
            head_limit=head_limit,
            ignore_case=ignore_case,
        )
    return {
        "pattern": pattern,
        "base": str(base),
        "engine": engine,
        "matches": matches,
        "truncated": len(matches) >= head_limit,
    }


def handle_shell_exec(params: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    _require_workspace_enabled(settings or get_settings())
    cfg = settings or get_settings()
    if not cfg.SHELL_EXEC_ENABLED:
        raise AgentFactoryException(
            "SHELL_DISABLED",
            "shell.exec is disabled (set SHELL_EXEC_ENABLED=true)",
            status_code=503,
        )
    command = str(params.get("command") or "").strip()
    if not command:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "command is required",
            status_code=400,
        )
    cwd_raw = params.get("cwd")
    if cwd_raw:
        cwd = resolve_workspace_path(str(cwd_raw), settings=cfg, must_exist=True)
        if not cwd.is_dir():
            raise AgentFactoryException(
                "INVALID_PARAMS",
                "cwd must be a directory",
                status_code=400,
            )
    else:
        cwd = workspace_root(cfg)
    timeout = float(params.get("timeout") or cfg.SHELL_EXEC_TIMEOUT_SECONDS)
    timeout = min(timeout, float(cfg.SHELL_EXEC_TIMEOUT_SECONDS))
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AgentFactoryException(
            "TIMEOUT",
            f"Command timed out after {timeout}s",
            status_code=408,
        ) from exc
    max_out = int(cfg.SHELL_EXEC_MAX_OUTPUT_CHARS)
    stdout = (proc.stdout or "")[:max_out]
    stderr = (proc.stderr or "")[:max_out]
    return {
        "command": command,
        "cwd": str(cwd),
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


async def handle_web_fetch_async(
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _require_workspace_enabled(settings or get_settings())
    cfg = settings or get_settings()
    if not cfg.WEB_FETCH_ENABLED:
        raise AgentFactoryException(
            "WEB_FETCH_DISABLED",
            "web.fetch is disabled (set WEB_FETCH_ENABLED=true)",
            status_code=503,
        )
    url = str(params.get("url") or "").strip()
    if not url:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "url is required",
            status_code=400,
        )
    prefixes = cfg.web_fetch_url_prefixes
    if prefixes and not any(url.startswith(p) for p in prefixes):
        raise AgentFactoryException(
            "FORBIDDEN",
            "URL not allowed by WEB_FETCH_URL_PREFIXES",
            status_code=403,
        )
    timeout = float(params.get("timeout") or cfg.WEB_FETCH_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise AgentFactoryException(
            "WEB_FETCH_TRANSPORT",
            "HTTP request failed",
            status_code=502,
        ) from exc
    ctype = resp.headers.get("content-type", "")
    text = resp.text[: int(cfg.WEB_FETCH_MAX_CHARS)]
    return {
        "url": url,
        "status_code": resp.status_code,
        "content_type": ctype,
        "content": text,
        "truncated": len(resp.text) > int(cfg.WEB_FETCH_MAX_CHARS),
    }


async def handle_web_search_async(
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    query = str(params.get("query") or "").strip()
    if not query:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "query is required",
            status_code=400,
        )
    top_k = params.get("top_k")
    top_k_int = int(top_k) if top_k is not None else None
    recency = params.get("search_recency_filter")
    recency_str = str(recency).strip() if isinstance(recency, str) and recency.strip() else None
    edition = params.get("edition")
    edition_str = str(edition).strip() if isinstance(edition, str) and edition.strip() else None
    block_raw = params.get("block_websites")
    block: list[str] | None = None
    if isinstance(block_raw, list):
        block = [str(x).strip() for x in block_raw if str(x).strip()]
    allowed_raw = params.get("allowed_sites")
    allowed: list[str] | None = None
    if isinstance(allowed_raw, list):
        allowed = [str(x).strip() for x in allowed_raw if str(x).strip()]
    return await post_baidu_web_search(
        cfg,
        query=query,
        top_k=top_k_int,
        edition=edition_str,
        search_recency_filter=recency_str,
        block_websites=block,
        allowed_sites=allowed,
    )


def dispatch_workspace_tool(
    tool_id: str,
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Sync workspace tool dispatch."""
    handlers = {
        "fs.read": handle_fs_read,
        "fs.write": handle_fs_write,
        "fs.edit": handle_fs_edit,
        "fs.apply_patch": handle_fs_apply_patch,
        "fs.glob": handle_fs_glob,
        "fs.grep": handle_fs_grep,
        "shell.exec": handle_shell_exec,
    }
    fn = handlers.get(tool_id)
    if fn is None:
        raise AgentFactoryException(
            "TOOL_NOT_IMPLEMENTED",
            f"Workspace tool {tool_id} requires async handler",
            status_code=501,
        )
    return fn(params, settings=settings)


async def dispatch_workspace_tool_async(
    tool_id: str,
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    if tool_id == "web.fetch":
        return await handle_web_fetch_async(params, settings=cfg)
    if tool_id == "web.search":
        return await handle_web_search_async(params, settings=cfg)
    if tool_id == "shell.exec":
        return await asyncio.to_thread(
            handle_shell_exec,
            params,
            settings=cfg,
        )
    return dispatch_workspace_tool(tool_id, params, settings=cfg)
