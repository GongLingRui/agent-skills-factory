"""OpenClaw nodes tool — worker/node registry and invoke."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agent_factory.config import Settings, get_settings
from agent_factory.middleware.error_handler import AgentFactoryException

logger = logging.getLogger(__name__)

NODES_TOOL_IDS: frozenset[str] = frozenset({"nodes.manage"})

_NODE_ACTIONS = frozenset(
    {
        "status",
        "describe",
        "pending",
        "approve",
        "reject",
        "notify",
        "invoke",
        "register",
        "unregister",
    }
)


@dataclass
class RegisteredNode:
    node_id: str
    name: str
    kind: str
    status: str
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at: str = ""


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, RegisteredNode] = {}
        self._pending: dict[str, dict[str, Any]] = {}

    def register(self, *, name: str, kind: str = "worker", capabilities: list[str] | None = None) -> RegisteredNode:
        nid = f"node_{uuid.uuid4().hex[:12]}"
        node = RegisteredNode(
            node_id=nid,
            name=name,
            kind=kind,
            status="online",
            capabilities=list(capabilities or []),
            registered_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
        )
        self._nodes[nid] = node
        return node

    def list_nodes(self) -> list[RegisteredNode]:
        return list(self._nodes.values())

    def get(self, node_id: str) -> RegisteredNode | None:
        return self._nodes.get(node_id)

    def remove(self, node_id: str) -> bool:
        return self._nodes.pop(node_id, None) is not None


_REGISTRY = NodeRegistry()


def _ensure_default_nodes(settings: Settings) -> None:
    if _REGISTRY.list_nodes():
        return
    for name in ("local-worker", "script-worker"):
        _REGISTRY.register(name=name, kind="worker", capabilities=["invoke", "script"])


async def handle_nodes_manage(
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    if not cfg.NODES_TOOLS_ENABLED:
        raise AgentFactoryException(
            "NODES_DISABLED",
            "nodes tool disabled (set NODES_TOOLS_ENABLED=true)",
            status_code=503,
        )
    action = str(params.get("action") or "status").strip().lower()
    if action not in _NODE_ACTIONS:
        raise AgentFactoryException(
            "INVALID_PARAMS", f"Unknown nodes action: {action}", status_code=400
        )
    _ensure_default_nodes(cfg)

    if action == "status":
        nodes = [
            {
                "nodeId": n.node_id,
                "name": n.name,
                "kind": n.kind,
                "status": n.status,
                "capabilities": n.capabilities,
            }
            for n in _REGISTRY.list_nodes()
        ]
        return {"nodes": nodes, "total": len(nodes)}

    node_ref = str(params.get("node") or params.get("nodeId") or "").strip()
    node = None
    if node_ref:
        node = _REGISTRY.get(node_ref)
        if node is None:
            for n in _REGISTRY.list_nodes():
                if n.name == node_ref:
                    node = n
                    break

    if action == "describe":
        if node is None:
            raise AgentFactoryException("NOT_FOUND", "Node not found", status_code=404)
        return {
            "nodeId": node.node_id,
            "name": node.name,
            "kind": node.kind,
            "status": node.status,
            "capabilities": node.capabilities,
            "metadata": node.metadata,
        }

    if action == "register":
        name = str(params.get("name") or node_ref or "node").strip()
        caps = params.get("capabilities")
        cap_list = [str(c) for c in caps] if isinstance(caps, list) else None
        n = _REGISTRY.register(name=name, kind=str(params.get("kind") or "worker"), capabilities=cap_list)
        return {"status": "registered", "nodeId": n.node_id, "name": n.name}

    if action == "unregister":
        if node is None:
            raise AgentFactoryException("NOT_FOUND", "Node not found", status_code=404)
        _REGISTRY.remove(node.node_id)
        return {"status": "unregistered", "nodeId": node.node_id}

    if action == "pending":
        return {"pending": list(_REGISTRY._pending.values())}

    if action == "approve":
        rid = str(params.get("requestId") or "").strip()
        if rid in _REGISTRY._pending:
            _REGISTRY._pending.pop(rid)
        return {"status": "approved", "requestId": rid}

    if action == "reject":
        rid = str(params.get("requestId") or "").strip()
        _REGISTRY._pending.pop(rid, None)
        return {"status": "rejected", "requestId": rid}

    if action == "notify":
        return {
            "status": "notified",
            "title": params.get("title"),
            "body": params.get("body"),
            "nodeId": node.node_id if node else None,
        }

    if action == "invoke":
        command = str(params.get("invokeCommand") or params.get("command") or "").strip()
        if not command:
            raise AgentFactoryException(
                "INVALID_PARAMS", "invokeCommand required", status_code=400
            )
        raw_params = params.get("invokeParamsJson") or params.get("params") or {}
        if isinstance(raw_params, str):
            try:
                invoke_params = json.loads(raw_params)
            except json.JSONDecodeError as exc:
                raise AgentFactoryException(
                    "INVALID_PARAMS", "invokeParamsJson must be JSON", status_code=400
                ) from exc
        elif isinstance(raw_params, dict):
            invoke_params = raw_params
        else:
            invoke_params = {}
        if command == "script.run" and cfg.SCRIPT_HOOKS_ENABLED:
            from agent_factory.workers.gvisor_runner import (
                gvisor_available,
                run_controlled_script_gvisor,
            )

            source = str(invoke_params.get("source") or "")
            if gvisor_available(cfg.SCRIPT_GVISOR_RUNSC):
                out = run_controlled_script_gvisor(
                    script_source=source,
                    hook_id="nodes.invoke",
                    input_payload=invoke_params,
                    runsc_path=cfg.SCRIPT_GVISOR_RUNSC,
                )
                return {"status": "ok", "command": command, "output": out}
        return {
            "status": "ok",
            "command": command,
            "nodeId": node.node_id if node else "local-worker",
            "params": invoke_params,
            "note": "Invoke dispatched (OpenClaw nodes parity)",
        }

    raise AgentFactoryException("INVALID_PARAMS", f"Unhandled action {action}", status_code=400)
