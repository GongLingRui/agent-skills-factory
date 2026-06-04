"""HTTP client for external kb.search (docs/09)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agent_factory.config import Settings
from agent_factory.core.url_safety import validate_outbound_http_url
from agent_factory.infra.model_queue import acquire_rerank_queue_slot
from agent_factory.infra.redis import get_redis
from agent_factory.services.degradation_runtime import DegradationRunKnobs
from agent_factory.services.kb_indexed_refs import (
    build_indexed_catalog,
    normalize_kb_results,
)

logger = logging.getLogger(__name__)


async def post_kb_search(
    settings: Settings,
    *,
    params: dict[str, Any],
    retrieval_scopes: list[str],
    indexed_references: list[Any] | None,
    degradation_knobs: DegradationRunKnobs | None,
) -> dict[str, Any] | None:
    """POST upstream KB; return dict with ``results`` list or ``None``."""
    url = (settings.KB_SEARCH_URL or "").strip()
    if not url:
        return None
    try:
        validate_outbound_http_url(
            url,
            allow_http=settings.KB_SEARCH_ALLOW_HTTP,
            allow_private_hosts=settings.KB_SEARCH_ALLOW_PRIVATE_HOSTS,
        )
    except ValueError as exc:
        logger.warning("kb.search URL rejected: %s", exc)
        return None
    query = str(params.get("query", ""))
    catalog = build_indexed_catalog(indexed_references)
    body: dict[str, Any] = {
        "query": query,
        "retrieval_scopes": list(retrieval_scopes),
    }
    if catalog:
        body["indexed_references"] = catalog
    elif indexed_references is not None:
        body["indexed_references"] = indexed_references
    if degradation_knobs is not None:
        if degradation_knobs.kb_top_k is not None:
            body["top_k"] = degradation_knobs.kb_top_k
        if degradation_knobs.skip_rerank:
            body["skip_rerank"] = True
    scope = params.get("scope")
    if scope is not None:
        body["scope"] = scope
    headers = {"Content-Type": "application/json"}
    tok = (settings.KB_SEARCH_BEARER_TOKEN or "").strip()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    timeout = httpx.Timeout(settings.KB_SEARCH_TIMEOUT_SECONDS)

    async def _do_post() -> httpx.Response:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.post(url, json=body, headers=headers)

    try:
        if getattr(settings, "MODEL_QUEUE_ENABLED", False):
            redis = get_redis()
            async with acquire_rerank_queue_slot(redis, settings):
                resp = await _do_post()
        else:
            resp = await _do_post()
    except Exception as exc:
        logger.warning("kb.search upstream transport error: %s", exc)
        return None
    if resp.status_code >= 400:
        logger.warning(
            "kb.search upstream HTTP %s: %s",
            resp.status_code,
            (resp.text or "")[:500],
        )
        return None
    try:
        data = resp.json()
    except Exception as exc:
        logger.warning("kb.search upstream JSON decode failed: %s", exc)
        return None
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return normalize_kb_results(data)
    return None
