"""OpenClaw ui.browser / ui.canvas tools."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.db.models.session_canvas_state import SessionCanvasState
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.mcp_tools import dispatch_mcp_tool

logger = logging.getLogger(__name__)

UI_TOOL_IDS: frozenset[str] = frozenset({"ui.browser", "ui.canvas"})

_BROWSER_ACTION_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "navigate": ("mcp.playwright.navigate", {"url": "url"}),
    "snapshot": ("mcp.playwright.snapshot", {}),
    "click": ("mcp.playwright.click", {"ref": "ref", "element": "element"}),
    "fill": ("mcp.playwright.fill", {"ref": "ref", "text": "text"}),
    "status": ("mcp.playwright.snapshot", {}),
}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _require_ui_enabled(settings: Settings) -> None:
    if not settings.UI_TOOLS_ENABLED:
        raise AgentFactoryException(
            "UI_DISABLED",
            "ui tools are disabled (set UI_TOOLS_ENABLED=true)",
            status_code=503,
        )


async def handle_ui_browser(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = db
    cfg = settings or get_settings()
    _require_ui_enabled(cfg)
    action = str(params.get("action") or "snapshot").strip().lower()
    if action in ("start", "stop", "profiles", "tabs", "open", "close", "focus"):
        return {
            "action": action,
            "status": "ok",
            "note": (
                "Headless Playwright MCP handles browser lifecycle; "
                f"action={action} acknowledged (OpenClaw browser parity)."
            ),
        }
    mapping = _BROWSER_ACTION_MAP.get(action)
    if mapping is None:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            f"Unsupported browser action: {action}",
            status_code=400,
        )
    tool_id, field_map = mapping
    mcp_params: dict[str, Any] = {}
    for mcp_key, src_key in field_map.items():
        if src_key in params and params[src_key] is not None:
            mcp_params[mcp_key] = params[src_key]
    if action == "navigate" and "url" not in mcp_params:
        url = params.get("targetUrl") or params.get("target_url")
        if url:
            mcp_params["url"] = url
    if action == "navigate" and "url" not in mcp_params:
        raise AgentFactoryException(
            "INVALID_PARAMS", "url is required for navigate", status_code=400
        )
    result = await dispatch_mcp_tool(tool_id, mcp_params, settings=cfg)
    return {"action": action, **result}


async def _load_canvas(db: AsyncSession, session_id: str) -> SessionCanvasState:
    q = await db.execute(
        select(SessionCanvasState).where(SessionCanvasState.session_id == session_id)
    )
    row = q.scalar_one_or_none()
    if row is None:
        row = SessionCanvasState(session_id=session_id, visible=False, updated_at=_utc_now())
        db.add(row)
        await db.flush()
    return row


async def handle_ui_canvas(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    session_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    _require_ui_enabled(cfg)
    action = str(params.get("action") or "").strip().lower()
    if not action:
        raise AgentFactoryException(
            "INVALID_PARAMS", "action is required", status_code=400
        )
    canvas = await _load_canvas(db, session_id)
    now = _utc_now()

    if action == "present":
        canvas.visible = True
        canvas.title = str(params.get("title") or canvas.title or "")[:256] or None
        url = params.get("url") or params.get("targetUrl")
        if isinstance(url, str) and url.strip():
            canvas.url = url.strip()
        canvas.updated_at = now
        return {"action": action, "visible": True, "url": canvas.url, "title": canvas.title}

    if action == "hide":
        canvas.visible = False
        canvas.updated_at = now
        return {"action": action, "visible": False}

    if action == "navigate":
        url = str(params.get("url") or "").strip()
        if not url:
            raise AgentFactoryException(
                "INVALID_PARAMS", "url is required", status_code=400
            )
        canvas.url = url
        canvas.visible = True
        canvas.updated_at = now
        return {"action": action, "url": url, "visible": True}

    if action == "eval":
        expr = str(params.get("expression") or params.get("script") or "").strip()
        canvas.eval_result = f"[server-side eval stub] expression length={len(expr)}"
        canvas.updated_at = now
        return {"action": action, "result": canvas.eval_result}

    if action == "snapshot":
        snap = canvas.snapshot_base64
        if not snap and canvas.url:
            try:
                nav = await dispatch_mcp_tool(
                    "mcp.playwright.navigate",
                    {"url": canvas.url},
                    settings=cfg,
                )
                shot = await dispatch_mcp_tool(
                    "mcp.playwright.snapshot", {}, settings=cfg
                )
                snap = _extract_snapshot_base64(shot) or _extract_snapshot_base64(nav)
                if snap:
                    canvas.snapshot_base64 = snap
            except AgentFactoryException:
                logger.debug("canvas snapshot via playwright failed", exc_info=True)
        canvas.updated_at = now
        return {
            "action": action,
            "snapshot": snap,
            "url": canvas.url,
            "format": "png" if snap else None,
        }

    if action == "a2ui_push":
        payload = params.get("payload") or params.get("a2ui")
        if not isinstance(payload, dict):
            raise AgentFactoryException(
                "INVALID_PARAMS", "payload object required", status_code=400
            )
        canvas.a2ui_payload = payload
        canvas.visible = True
        canvas.updated_at = now
        return {"action": action, "a2ui": payload}

    if action == "a2ui_reset":
        canvas.a2ui_payload = None
        canvas.updated_at = now
        return {"action": action, "reset": True}

    raise AgentFactoryException(
        "INVALID_PARAMS",
        f"Unsupported canvas action: {action}",
        status_code=400,
    )


def _extract_snapshot_base64(result: dict[str, Any]) -> str | None:
    for key in ("snapshot", "image", "base64", "screenshot"):
        val = result.get(key)
        if isinstance(val, str) and len(val) > 100:
            return val
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image":
                data = block.get("data") or block.get("base64")
                if isinstance(data, str):
                    return data
    return None
