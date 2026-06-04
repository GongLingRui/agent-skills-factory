"""OpenClaw memory_search / memory_get tools."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.db.models.checkpoint import Checkpoint
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.memory_store import (
    memory_agent_root,
    read_memory_file,
    search_memory_files,
)
from agent_factory.services.user_agent_memory_service import fetch_cross_session_summary

MEMORY_TOOL_IDS: frozenset[str] = frozenset({"memory.search", "memory.get"})


def _require_memory_enabled(settings: Settings) -> None:
    if not settings.MEMORY_TOOLS_ENABLED:
        raise AgentFactoryException(
            "MEMORY_DISABLED",
            "memory tools are disabled (set MEMORY_TOOLS_ENABLED=true)",
            status_code=503,
        )


async def _search_sessions_corpus(
    db: AsyncSession,
    *,
    user_id_hash: str,
    agent_id: str,
    query: str,
    max_results: int,
) -> list[dict[str, Any]]:
    q = query.lower()
    tokens = [t for t in re.findall(r"[\w\u4e00-\u9fff]+", q) if len(t) >= 2][:8]
    if not tokens:
        return []

    xs = await fetch_cross_session_summary(
        db, user_id_hash=user_id_hash, agent_id=agent_id
    )
    hits: list[dict[str, Any]] = []
    if xs:
        hay = xs.lower()
        score = sum(1 for t in tokens if t in hay) / max(len(tokens), 1)
        if score > 0:
            hits.append(
                {
                    "path": "sessions/cross_session_summary.md",
                    "score": round(score, 4),
                    "snippet": xs[:400],
                    "startLine": 1,
                    "endLine": min(20, xs.count("\n") + 1),
                    "source": "sessions",
                }
            )

    cp_rows = await db.execute(
        select(Checkpoint.session_id, Checkpoint.session_memory, Checkpoint.run_id)
        .where(Checkpoint.session_id.isnot(None))
        .order_by(Checkpoint.timestamp.desc())
        .limit(30)
    )
    for sid, smem, rid in cp_rows.all():
        if not smem:
            continue
        text = str(smem)
        if isinstance(smem, dict):
            text = "\n".join(f"{k}: {v}" for k, v in smem.items())
        hay = text.lower()
        score = sum(1 for t in tokens if t in hay) / max(len(tokens), 1)
        if score <= 0:
            continue
        hits.append(
            {
                "path": f"sessions/{sid}/session_memory.json",
                "score": round(score * 0.9, 4),
                "snippet": text[:400],
                "startLine": 1,
                "endLine": 10,
                "source": "sessions",
                "runId": rid,
            }
        )
        if len(hits) >= max_results:
            break
    return hits[:max_results]


async def handle_memory_search(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    user_id_hash: str,
    agent_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    _require_memory_enabled(cfg)
    query = str(params.get("query") or "").strip()
    if not query:
        raise AgentFactoryException(
            "INVALID_PARAMS", "query is required", status_code=400
        )
    max_results = int(params.get("maxResults") or params.get("max_results") or 10)
    max_results = max(1, min(max_results, 50))
    min_score = float(params.get("minScore") or params.get("min_score") or 0.0)
    corpus = str(params.get("corpus") or "all").strip().lower()

    results: list[dict[str, Any]] = []
    if corpus in ("memory", "all", "wiki"):
        mem_root = memory_agent_root(
            user_id_hash=user_id_hash, agent_id=agent_id, settings=cfg
        )
        for hit in search_memory_files(
            mem_root, query, max_results=max_results, min_score=min_score
        ):
            results.append(
                {
                    "path": hit.path,
                    "score": hit.score,
                    "snippet": hit.snippet,
                    "startLine": hit.start_line,
                    "endLine": hit.end_line,
                    "source": hit.source,
                    "corpus": "memory",
                }
            )

    if corpus in ("sessions", "all"):
        session_hits = await _search_sessions_corpus(
            db,
            user_id_hash=user_id_hash,
            agent_id=agent_id,
            query=query,
            max_results=max_results,
        )
        results.extend(session_hits)

    results.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    return {
        "query": query,
        "corpus": corpus,
        "results": results[:max_results],
        "total": len(results[:max_results]),
    }


async def handle_memory_get(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    user_id_hash: str,
    agent_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = db
    cfg = settings or get_settings()
    _require_memory_enabled(cfg)
    path = str(params.get("path") or "").strip()
    if not path:
        raise AgentFactoryException(
            "INVALID_PARAMS", "path is required", status_code=400
        )
    corpus = str(params.get("corpus") or "memory").strip().lower()
    from_line = int(params.get("from") or params.get("from_line") or 1)
    lines = params.get("lines")
    line_count = int(lines) if lines is not None else None
    default_lines = int(cfg.MEMORY_GET_DEFAULT_LINES)

    if path.startswith("sessions/") or corpus == "sessions":
        if path.endswith("cross_session_summary.md"):
            summary = await fetch_cross_session_summary(
                db, user_id_hash=user_id_hash, agent_id=agent_id
            )
            content = summary or ""
            chunk_lines = content.splitlines()
            start = max(1, from_line)
            limit = line_count or default_lines
            body = "\n".join(chunk_lines[start - 1 : start - 1 + limit])
            return {
                "path": path,
                "corpus": "sessions",
                "from": start,
                "lines": min(limit, len(chunk_lines)),
                "content": body,
            }
        raise AgentFactoryException(
            "NOT_FOUND",
            f"Session memory path not readable: {path}",
            status_code=404,
        )

    mem_root = memory_agent_root(
        user_id_hash=user_id_hash, agent_id=agent_id, settings=cfg
    )
    try:
        data = read_memory_file(
            mem_root,
            path,
            from_line=from_line,
            line_count=line_count,
            default_lines=default_lines,
        )
    except FileNotFoundError as exc:
        raise AgentFactoryException(
            "NOT_FOUND", f"Memory file not found: {path}", status_code=404
        ) from exc
    except ValueError as exc:
        raise AgentFactoryException("FORBIDDEN", str(exc), status_code=403) from exc
    data["corpus"] = "memory"
    return data
