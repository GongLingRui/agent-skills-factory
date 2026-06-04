"""MCP-backed tools: Context7 docs + Playwright browser."""

from __future__ import annotations

import logging
from typing import Any

from agent_factory.config import Settings, get_settings
from agent_factory.core.tool_catalog import TOOL_BY_ID
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.mcp_stdio_client import McpServerConfig, mcp_call_tool

logger = logging.getLogger(__name__)

MCP_TOOL_IDS: frozenset[str] = frozenset(
    t.id for t in TOOL_BY_ID.values() if t.implemented and t.id.startswith("mcp.")
)


def _server_config(settings: Settings, server_name: str) -> McpServerConfig:
    if server_name == "context7":
        if not settings.MCP_CONTEXT7_ENABLED:
            raise AgentFactoryException(
                "MCP_DISABLED",
                "Context7 MCP 未启用",
                status_code=503,
            )
        cmd = (settings.MCP_CONTEXT7_COMMAND or "npx").strip()
        args = tuple(
            a.strip()
            for a in (settings.MCP_CONTEXT7_ARGS or "-y,@upstash/context7-mcp@latest").split(",")
            if a.strip()
        )
        return McpServerConfig("context7", cmd, args)
    if server_name == "playwright":
        if not settings.MCP_PLAYWRIGHT_ENABLED:
            raise AgentFactoryException(
                "MCP_DISABLED",
                "Playwright MCP 未启用",
                status_code=503,
            )
        cmd = (settings.MCP_PLAYWRIGHT_COMMAND or "npx").strip()
        args = tuple(
            a.strip()
            for a in (settings.MCP_PLAYWRIGHT_ARGS or "-y,@playwright/mcp@latest").split(",")
            if a.strip()
        )
        return McpServerConfig("playwright", cmd, args)
    raise AgentFactoryException(
        "MCP_UNKNOWN",
        f"Unknown MCP server: {server_name}",
        status_code=500,
    )


async def dispatch_mcp_tool(
    tool_id: str,
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    desc = TOOL_BY_ID.get(tool_id)
    if desc is None or not desc.mcp_server or not desc.mcp_tool:
        raise AgentFactoryException(
            "TOOL_NOT_IMPLEMENTED",
            f"MCP tool not configured: {tool_id}",
            status_code=501,
        )
    server = _server_config(cfg, desc.mcp_server)
    try:
        result = await mcp_call_tool(
            server,
            desc.mcp_tool,
            params,
            timeout_seconds=float(cfg.MCP_CALL_TIMEOUT_SECONDS),
        )
    except AgentFactoryException:
        raise
    except FileNotFoundError as exc:
        raise AgentFactoryException(
            "MCP_UNAVAILABLE",
            f"MCP 命令不可用（请安装 Node/npx 并配置 {desc.mcp_server}）",
            status_code=503,
        ) from exc
    except Exception as exc:
        logger.exception("mcp tool failed: %s", tool_id)
        raise AgentFactoryException(
            "MCP_TOOL_FAILED",
            f"MCP 工具 {tool_id} 执行失败: {exc}",
            status_code=502,
        ) from exc
    return {
        "tool_id": tool_id,
        "mcp_server": desc.mcp_server,
        "mcp_tool": desc.mcp_tool,
        "result": result,
    }
