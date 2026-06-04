"""OpenClaw-style markdown memory store with FTS5 indexing."""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_factory.config import Settings, get_settings
from agent_factory.core.workspace_sandbox import workspace_root


@dataclass(frozen=True)
class MemoryHit:
    path: str
    score: float
    snippet: str
    start_line: int
    end_line: int
    source: str  # memory | sessions


_INDEX_LOCK = threading.Lock()


def memory_agent_root(
    *,
    user_id_hash: str,
    agent_id: str,
    settings: Settings | None = None,
) -> Path:
    cfg = settings or get_settings()
    root = workspace_root(cfg) / ".agent-factory" / "memory" / user_id_hash / agent_id
    root.mkdir(parents=True, exist_ok=True)
    (root / "memory").mkdir(parents=True, exist_ok=True)
    mem_file = root / "MEMORY.md"
    if not mem_file.is_file():
        mem_file.write_text(
            "# Memory\n\nPersistent notes for this agent.\n",
            encoding="utf-8",
        )
    return root


def _index_db_path(mem_root: Path) -> Path:
    return mem_root / "memory_index.sqlite"


def _iter_memory_files(mem_root: Path) -> list[Path]:
    files: list[Path] = []
    main = mem_root / "MEMORY.md"
    if main.is_file():
        files.append(main)
    mem_dir = mem_root / "memory"
    if mem_dir.is_dir():
        files.extend(sorted(mem_dir.rglob("*.md")))
    return files


def _rel_path(mem_root: Path, path: Path) -> str:
    return str(path.relative_to(mem_root)).replace("\\", "/")


def rebuild_memory_index(mem_root: Path) -> int:
    """Rebuild FTS index for all markdown files under mem_root."""
    db_path = _index_db_path(mem_root)
    with _INDEX_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("DROP TABLE IF EXISTS memory_fts")
            conn.execute(
                "CREATE VIRTUAL TABLE memory_fts USING fts5("
                "path UNINDEXED, content, tokenize='unicode61'"
                ")"
            )
            count = 0
            for fp in _iter_memory_files(mem_root):
                text = fp.read_text(encoding="utf-8", errors="replace")
                conn.execute(
                    "INSERT INTO memory_fts(path, content) VALUES (?, ?)",
                    (_rel_path(mem_root, fp), text),
                )
                count += 1
            conn.commit()
            return count
        finally:
            conn.close()


def _ensure_index(mem_root: Path) -> None:
    db_path = _index_db_path(mem_root)
    if not db_path.is_file():
        rebuild_memory_index(mem_root)
        return
    latest_mtime = 0.0
    for fp in _iter_memory_files(mem_root):
        latest_mtime = max(latest_mtime, fp.stat().st_mtime)
    if latest_mtime > db_path.stat().st_mtime:
        rebuild_memory_index(mem_root)


def search_memory_files(
    mem_root: Path,
    query: str,
    *,
    max_results: int = 10,
    min_score: float = 0.0,
) -> list[MemoryHit]:
    _ensure_index(mem_root)
    q = query.strip()
    if not q:
        return []
    db_path = _index_db_path(mem_root)
    with _INDEX_LOCK:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT path, snippet(memory_fts, 1, '[', ']', '…', 20) AS snip, "
                "bm25(memory_fts) AS rank "
                "FROM memory_fts WHERE memory_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (_fts_query(q), max(max_results * 3, 10)),
            ).fetchall()
        except sqlite3.OperationalError:
            rebuild_memory_index(mem_root)
            rows = conn.execute(
                "SELECT path, snippet(memory_fts, 1, '[', ']', '…', 20) AS snip, "
                "bm25(memory_fts) AS rank "
                "FROM memory_fts WHERE memory_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (_fts_query(q), max(max_results * 3, 10)),
            ).fetchall()
        finally:
            conn.close()

    hits: list[MemoryHit] = []
    for row in rows:
        rank = float(row["rank"] or 0)
        score = max(0.0, 1.0 / (1.0 + abs(rank)))
        if score < min_score:
            continue
        path = str(row["path"])
        snippet = str(row["snip"] or "")
        start_line, end_line = _snippet_line_range(mem_root, path, snippet)
        hits.append(
            MemoryHit(
                path=path,
                score=round(score, 4),
                snippet=snippet,
                start_line=start_line,
                end_line=end_line,
                source="memory",
            )
        )
        if len(hits) >= max_results:
            break
    return hits


def _fts_query(raw: str) -> str:
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", raw)
    if not tokens:
        return raw
    return " OR ".join(f'"{t}"' for t in tokens[:12])


def _snippet_line_range(mem_root: Path, rel: str, snippet: str) -> tuple[int, int]:
    fp = mem_root / rel
    if not fp.is_file():
        return 1, 1
    needle = snippet.replace("[", "").replace("]", "").replace("…", "").strip()
    if len(needle) < 4:
        return 1, min(20, sum(1 for _ in fp.open(encoding="utf-8")))
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines, start=1):
        if needle[: min(32, len(needle))] in line:
            return i, min(i + 10, len(lines))
    return 1, min(20, len(lines))


def read_memory_file(
    mem_root: Path,
    path: str,
    *,
    from_line: int = 1,
    line_count: int | None = None,
    default_lines: int = 200,
) -> dict[str, Any]:
    rel = path.strip().lstrip("/")
    if rel in ("MEMORY.md", "memory.md"):
        fp = mem_root / "MEMORY.md"
    elif rel.startswith("memory/"):
        fp = mem_root / rel
    else:
        fp = mem_root / rel
    resolved = fp.resolve()
    if not str(resolved).startswith(str(mem_root.resolve())):
        raise ValueError("path escapes memory root")
    if not resolved.is_file():
        raise FileNotFoundError(path)
    lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, int(from_line))
    limit = int(line_count) if line_count is not None else default_lines
    limit = max(1, min(limit, 2000))
    chunk = lines[start - 1 : start - 1 + limit]
    truncated = (start - 1 + limit) < len(lines)
    return {
        "path": _rel_path(mem_root, resolved),
        "from": start,
        "lines": len(chunk),
        "total_lines": len(lines),
        "truncated": truncated,
        "content": "\n".join(chunk),
    }
