"""Minimal MCP stdio JSON-RPC client for backend tool bridge."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from agent_factory.middleware.error_handler import AgentFactoryException

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    command: str
    args: tuple[str, ...]


class McpStdioClient:
    """One-shot MCP session: initialize → tools/call → shutdown."""

    def __init__(self, *, timeout_seconds: float = 60.0) -> None:
        self._timeout = timeout_seconds
        self._seq = 0

    async def call_tool(
        self,
        server: McpServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        proc = await asyncio.create_subprocess_exec(
            server.command,
            *server.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin and proc.stdout

        async def _write(msg: dict[str, Any]) -> None:
            line = json.dumps(msg, ensure_ascii=False) + "\n"
            proc.stdin.write(line.encode("utf-8"))
            await proc.stdin.drain()

        async def _read_response(req_id: int) -> dict[str, Any]:
            deadline = asyncio.get_event_loop().time() + self._timeout
            while asyncio.get_event_loop().time() < deadline:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=self._timeout)
                if not raw:
                    break
                try:
                    msg = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == req_id:
                    if "error" in msg:
                        err = msg["error"]
                        raise AgentFactoryException(
                            "MCP_TOOL_ERROR",
                            str(err.get("message") or err),
                            status_code=502,
                        )
                    return msg.get("result") or {}
            raise AgentFactoryException(
                "MCP_TIMEOUT",
                f"MCP server {server.name} timed out",
                status_code=504,
            )

        try:
            self._seq += 1
            init_id = self._seq
            await _write(
                {
                    "jsonrpc": "2.0",
                    "id": init_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "agent-factory", "version": "0.1.0"},
                    },
                }
            )
            await _read_response(init_id)
            await _write({"jsonrpc": "2.0", "method": "notifications/initialized"})

            self._seq += 1
            call_id = self._seq
            await _write(
                {
                    "jsonrpc": "2.0",
                    "id": call_id,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                }
            )
            result = await _read_response(call_id)
            content = result.get("content")
            if isinstance(content, list):
                texts = [
                    str(c.get("text"))
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                joined = "\n".join(t for t in texts if t)
                if joined:
                    return {"text": joined, "raw": result}
            return result
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                proc.kill()


async def mcp_call_tool(
    server: McpServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout_seconds: float = 60.0,
) -> Any:
    client = McpStdioClient(timeout_seconds=timeout_seconds)
    return await client.call_tool(server, tool_name, arguments)
