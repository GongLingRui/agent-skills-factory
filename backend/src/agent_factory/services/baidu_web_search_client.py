"""Baidu Qianfan AI Search (web_search) client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agent_factory.config import Settings
from agent_factory.middleware.error_handler import AgentFactoryException

logger = logging.getLogger(__name__)

_DEFAULT_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"
_RECENCY_VALUES = frozenset({"week", "month", "semiyear", "year"})


def _normalize_references(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        out.append(
            {
                "id": item.get("id"),
                "title": str(item.get("title") or item.get("web_anchor") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "snippet": content,
                "date": str(item.get("date") or "").strip() or None,
                "type": str(item.get("type") or "web"),
            }
        )
    return out


def _build_request_body(
    *,
    query: str,
    top_k: int,
    edition: str,
    search_recency_filter: str | None,
    block_websites: list[str] | None,
    allowed_sites: list[str] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "messages": [{"role": "user", "content": query}],
        "search_source": "baidu_search_v2",
        "resource_type_filter": [{"type": "web", "top_k": top_k}],
    }
    if edition in ("standard", "lite"):
        body["edition"] = edition
    if search_recency_filter in _RECENCY_VALUES:
        body["search_recency_filter"] = search_recency_filter
    if block_websites:
        body["block_websites"] = block_websites
    if allowed_sites:
        body["search_filter"] = {"match": {"site": allowed_sites}}
    return body


async def post_baidu_web_search(
    settings: Settings,
    *,
    query: str,
    top_k: int | None = None,
    edition: str | None = None,
    search_recency_filter: str | None = None,
    block_websites: list[str] | None = None,
    allowed_sites: list[str] | None = None,
) -> dict[str, Any]:
    """Call Baidu Qianfan web_search and return normalized hits."""
    api_key = (settings.BAIDU_WEB_SEARCH_API_KEY or "").strip()
    if not api_key:
        raise AgentFactoryException(
            "WEB_SEARCH_NOT_CONFIGURED",
            "未配置 BAIDU_WEB_SEARCH_API_KEY",
            status_code=503,
        )
    if not settings.WEB_SEARCH_ENABLED:
        raise AgentFactoryException(
            "WEB_SEARCH_DISABLED",
            "web.search 已关闭（设置 WEB_SEARCH_ENABLED=true）",
            status_code=503,
        )
    q = query.strip()
    if not q:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "query is required",
            status_code=400,
        )
    k = int(top_k if top_k is not None else settings.BAIDU_WEB_SEARCH_DEFAULT_TOP_K)
    k = max(1, min(k, settings.BAIDU_WEB_SEARCH_MAX_TOP_K))
    url = (settings.BAIDU_WEB_SEARCH_URL or _DEFAULT_URL).strip()
    body = _build_request_body(
        query=q,
        top_k=k,
        edition=(edition or settings.BAIDU_WEB_SEARCH_EDITION or "standard").strip(),
        search_recency_filter=search_recency_filter,
        block_websites=block_websites,
        allowed_sites=allowed_sites,
    )
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Appbuilder-Authorization": f"Bearer {api_key}",
    }
    timeout = httpx.Timeout(float(settings.BAIDU_WEB_SEARCH_TIMEOUT_SECONDS))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("baidu web.search transport error: %s", exc)
        raise AgentFactoryException(
            "WEB_SEARCH_TRANSPORT",
            "百度搜索 API 请求失败",
            status_code=502,
        ) from exc
    try:
        payload = resp.json()
    except Exception as exc:
        logger.warning(
            "baidu web.search bad JSON: status=%s body=%s",
            resp.status_code,
            (resp.text or "")[:500],
        )
        raise AgentFactoryException(
            "WEB_SEARCH_UPSTREAM",
            "百度搜索 API 返回非 JSON",
            status_code=502,
        ) from exc
    if not isinstance(payload, dict):
        raise AgentFactoryException(
            "WEB_SEARCH_UPSTREAM",
            "百度搜索 API 响应格式异常",
            status_code=502,
        )
    code = payload.get("code")
    if resp.status_code >= 400 or (code is not None and str(code) not in ("", "0")):
        msg = str(payload.get("message") or resp.text or "upstream error")[:500]
        raise AgentFactoryException(
            "WEB_SEARCH_UPSTREAM",
            f"百度搜索 API 错误: {msg}",
            status_code=502 if resp.status_code >= 500 else 400,
        )
    results = _normalize_references(payload.get("references"))
    return {
        "query": q,
        "provider": "baidu_qianfan",
        "request_id": payload.get("request_id"),
        "results": results,
        "total": len(results),
    }
