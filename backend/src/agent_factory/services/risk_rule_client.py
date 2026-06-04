"""HTTP client for partner risk.rule_check (docs/09)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agent_factory.config import Settings
from agent_factory.core.url_safety import validate_outbound_http_url

logger = logging.getLogger(__name__)


async def post_risk_rule_check(
    settings: Settings,
    *,
    text: str,
) -> dict[str, Any] | None:
    """POST upstream risk API; return structured dict or ``None``."""
    url = (settings.RISK_RULE_CHECK_URL or "").strip()
    if not url:
        return None
    try:
        validate_outbound_http_url(
            url,
            allow_http=settings.RISK_RULE_CHECK_ALLOW_HTTP,
            allow_private_hosts=settings.RISK_RULE_CHECK_ALLOW_PRIVATE_HOSTS,
        )
    except ValueError as exc:
        logger.warning("risk.rule_check URL rejected: %s", exc)
        return None
    headers = {"Content-Type": "application/json"}
    tok = (settings.RISK_RULE_CHECK_BEARER_TOKEN or "").strip()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    body = {"text": text, "clause": text}
    timeout = httpx.Timeout(settings.RISK_RULE_CHECK_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
    except Exception as exc:
        logger.warning("risk.rule_check upstream transport error: %s", exc)
        return None
    if resp.status_code >= 400:
        logger.warning(
            "risk.rule_check upstream HTTP %s: %s",
            resp.status_code,
            (resp.text or "")[:500],
        )
        return None
    try:
        data = resp.json()
    except Exception as exc:
        logger.warning("risk.rule_check upstream JSON failed: %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    if "risk_level" not in data:
        return None
    return data
