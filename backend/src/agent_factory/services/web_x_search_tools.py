"""OpenClaw x_search tool — search X (Twitter) posts."""

from __future__ import annotations

from typing import Any

import httpx

from agent_factory.config import Settings, get_settings
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.baidu_web_search_client import post_baidu_web_search

WEB_X_SEARCH_TOOL_IDS: frozenset[str] = frozenset({"web.x_search"})


async def handle_web_x_search(
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    if not cfg.WEB_X_SEARCH_ENABLED and not cfg.WEB_SEARCH_ENABLED:
        raise AgentFactoryException(
            "X_SEARCH_DISABLED",
            "web.x_search disabled (set WEB_X_SEARCH_ENABLED or WEB_SEARCH_ENABLED)",
            status_code=503,
        )
    query = str(params.get("query") or params.get("q") or "").strip()
    if not query:
        raise AgentFactoryException(
            "INVALID_PARAMS", "query is required", status_code=400
        )
    max_results = int(params.get("maxResults") or params.get("max_results") or 10)
    max_results = max(1, min(max_results, 30))

    if cfg.X_SEARCH_API_URL:
        async with httpx.AsyncClient(timeout=float(cfg.X_SEARCH_TIMEOUT_SECONDS)) as client:
            resp = await client.post(
                cfg.X_SEARCH_API_URL.strip(),
                json={"query": query, "max_results": max_results},
                headers=(
                    {"Authorization": f"Bearer {cfg.X_SEARCH_API_KEY}"}
                    if cfg.X_SEARCH_API_KEY
                    else {}
                ),
            )
            if resp.status_code >= 400:
                raise AgentFactoryException(
                    "UPSTREAM_ERROR",
                    f"X search API HTTP {resp.status_code}",
                    status_code=502,
                )
            data = resp.json()
            if isinstance(data, dict) and "results" in data:
                return data
            return {"query": query, "results": data if isinstance(data, list) else [data]}

    # Fallback: site-restricted web search (OpenClaw-style when no dedicated X API)
    scoped = f"({query}) (site:x.com OR site:twitter.com)"
    raw = await post_baidu_web_search(
        cfg,
        query=scoped,
        top_k=max_results,
    )
    results = []
    for item in raw.get("results") or []:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or item.get("link") or "",
                "snippet": item.get("snippet") or item.get("content") or "",
                "source": "x.com",
            }
        )
    return {"query": query, "results": results, "engine": "web_search_fallback"}
