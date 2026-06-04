"""Feishu/Lark bot webhook and channel status."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from agent_factory.config import get_settings
from agent_factory.services.feishu_transport import handle_feishu_webhook_request

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status")
async def feishu_status() -> dict[str, Any]:
    s = get_settings()
    return {
        "enabled": s.FEISHU_ENABLED,
        "connection_mode": s.FEISHU_CONNECTION_MODE,
        "configured": bool(s.FEISHU_APP_ID.strip() and s.FEISHU_APP_SECRET.strip()),
        "candidate_agents": s.feishu_candidate_agent_ids,
        "default_agent_id": s.FEISHU_DEFAULT_AGENT_ID or None,
    }


@router.post("/events")
async def feishu_events(request: Request) -> JSONResponse:
    s = get_settings()
    if not s.FEISHU_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "FEISHU_DISABLED", "message": "Feishu channel disabled"}},
        )
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        result = await handle_feishu_webhook_request(headers, body)
    except Exception as exc:
        logger.exception("feishu_webhook_failed")
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "FEISHU_WEBHOOK_ERROR", "message": str(exc)[:200]}},
        )
    return JSONResponse(content=result)
