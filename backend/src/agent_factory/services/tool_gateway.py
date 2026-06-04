"""Tool Gateway: permission hard-check, rate-limit stub, tool execution.

See docs/09 and docs/34.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import get_settings
from agent_factory.core.document_text_extract import extract_plain_text
from agent_factory.core.read_reference import (
    find_lazy_reference_entry,
    resolve_reference_text,
    verify_reference_manifest_hash,
)
from agent_factory.db.models.file_upload import FileUpload
from agent_factory.db.models.run_spec import RunSpec
from agent_factory.db.models.skill import Skill
from agent_factory.db.models.tool import Tool
from agent_factory.infra.embedding_batch import get_embedding_broker
from agent_factory.infra.minio_client import MinioClient
from agent_factory.infra.redis import get_redis
from agent_factory.infra.tool_circuit_breaker import (
    assert_http_tool_circuit_closed,
    build_http_tool_circuit_config,
    clear_http_tool_failures,
    failure_counts_toward_circuit,
    http_tool_circuit_scope,
    record_http_tool_failure,
)
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.degradation_runtime import DegradationRunKnobs
from agent_factory.services.kb_search_client import post_kb_search
from agent_factory.services.risk_rule_client import post_risk_rule_check
from agent_factory.services.risk_rule_engine import evaluate_rules
from agent_factory.core.tool_catalog import READ_ONLY_TOOL_IDS
from agent_factory.core.user_context import UserContext
from agent_factory.services.agent_spawn_tool import (
    AGENT_TOOL_IDS,
    handle_agent_list,
    handle_agent_spawn,
)
from agent_factory.services.feishu_doc_tools import (
    FEISHU_TOOL_IDS,
    handle_feishu_doc,
)
from agent_factory.services.mcp_tools import MCP_TOOL_IDS, dispatch_mcp_tool
from agent_factory.services.openclaw_tools import (
    OPENCLAW_RUNTIME_TOOL_IDS,
    dispatch_openclaw_tool_async,
)
from agent_factory.services.workspace_tools import (
    WORKSPACE_TOOL_IDS,
    dispatch_workspace_tool,
    dispatch_workspace_tool_async,
)
from agent_factory.services.skill_bundle_storage import (
    extract_text_from_tarball,
    get_skill_bundle_bytes,
    verify_bundle_hash,
)

logger = logging.getLogger(__name__)

_BUILTIN_ASYNC_ONLY = (
    frozenset({"web.fetch", "web.search"})
    | MCP_TOOL_IDS
    | AGENT_TOOL_IDS
    | FEISHU_TOOL_IDS
    | OPENCLAW_RUNTIME_TOOL_IDS
)


def _indexed_refs_for_kb(run_spec: RunSpec | None) -> list[Any] | None:
    """RunSpec JSONB list for kb.search upstream (prd indexed retrieval)."""
    if run_spec is None:
        return None
    raw = run_spec.indexed_references
    if not isinstance(raw, list):
        return None
    return list(raw)


class ToolGateway:
    """Execute tools with RunSpec whitelist validation."""

    def __init__(self) -> None:
        # P0 built-in tool handlers (take precedence over Registry rows with same id).
        self._handlers: dict[str, Any] = {
            "kb.search": self._handle_kb_search,
            "doc.extract": self._handle_doc_extract,
            "read_reference": self._handle_read_reference,
            "risk.rule_check": self._handle_risk_rule_check,
            **{tid: self._handle_extended_tool for tid in WORKSPACE_TOOL_IDS},
            **{tid: self._handle_extended_tool for tid in MCP_TOOL_IDS},
            **{tid: self._handle_extended_tool for tid in AGENT_TOOL_IDS},
            **{tid: self._handle_extended_tool for tid in FEISHU_TOOL_IDS},
            **{tid: self._handle_extended_tool for tid in OPENCLAW_RUNTIME_TOOL_IDS},
        }

    def validate_and_run(
        self,
        *,
        tool_id: str,
        params: dict[str, Any],
        allowed_tools: list[str],
        retrieval_scopes: list[str],
    ) -> dict[str, Any]:
        """Sync path: built-in handlers only (tests / legacy callers)."""
        self._check_allowlist(tool_id, allowed_tools)
        if tool_id in WORKSPACE_TOOL_IDS:
            if tool_id in _BUILTIN_ASYNC_ONLY:
                raise AgentFactoryException(
                    "ASYNC_REQUIRED",
                    f"{tool_id} requires validate_and_run_async",
                    status_code=501,
                )
            return dispatch_workspace_tool(
                tool_id,
                params,
                settings=get_settings(),
            )
        handler = self._handlers.get(tool_id)
        if handler is None:
            raise AgentFactoryException(
                "TOOL_NOT_FOUND",
                f"Tool {tool_id} not implemented (sync path has no registry)",
                status_code=501,
            )
        return handler(params=params, retrieval_scopes=retrieval_scopes)

    async def validate_and_run_async(
        self,
        db: AsyncSession,
        *,
        tool_id: str,
        params: dict[str, Any],
        allowed_tools: list[str],
        retrieval_scopes: list[str],
        department: str | None = None,
        run_spec: RunSpec | None = None,
        caller_permissions: frozenset[str] | None = None,
        degradation_knobs: DegradationRunKnobs | None = None,
        session_id: str | None = None,
        model_gateway: Any | None = None,
    ) -> dict[str, Any]:
        """Resolve built-in handler first, else Tool Registry (http_api)."""
        self._check_allowlist(tool_id, allowed_tools)
        handler = self._handlers.get(tool_id)
        if handler is not None:
            if tool_id == "doc.extract":
                return await self._handle_doc_extract_async(
                    db,
                    params=params,
                    retrieval_scopes=retrieval_scopes,
                )
            if tool_id == "kb.search":
                return await self._handle_kb_search_async(
                    params=params,
                    retrieval_scopes=retrieval_scopes,
                    indexed_references=_indexed_refs_for_kb(run_spec),
                    degradation_knobs=degradation_knobs,
                )
            if tool_id == "read_reference":
                if run_spec is None:
                    raise AgentFactoryException(
                        "RUNSPEC_REQUIRED",
                        "read_reference requires RunSpec context",
                        status_code=500,
                    )
                return await self._handle_read_reference_async(
                    db,
                    run_spec=run_spec,
                    params=params,
                    retrieval_scopes=retrieval_scopes,
                )
            if tool_id == "risk.rule_check":
                return await self._handle_risk_rule_check_async(
                    params=params,
                    retrieval_scopes=retrieval_scopes,
                )
            if tool_id in WORKSPACE_TOOL_IDS:
                return await dispatch_workspace_tool_async(
                    tool_id,
                    params,
                    settings=get_settings(),
                )
            if tool_id in MCP_TOOL_IDS:
                return await dispatch_mcp_tool(
                    tool_id,
                    params,
                    settings=get_settings(),
                )
            if tool_id == "agent.list":
                return await handle_agent_list(db, params)
            if tool_id == "agent.spawn":
                if run_spec is None:
                    raise AgentFactoryException(
                        "RUNSPEC_REQUIRED",
                        "agent.spawn requires RunSpec context",
                        status_code=500,
                    )
                from agent_factory.services.factory import get_model_gateway

                user_ctx = UserContext(
                    session_id=session_id or "",
                    user_id_hash=str(run_spec.user_id_hash or ""),
                    department=department,
                    permissions=tuple(caller_permissions or ()),
                )
                gw = model_gateway if model_gateway is not None else get_model_gateway()
                return await handle_agent_spawn(
                    db,
                    params,
                    user_ctx=user_ctx,
                    model_gateway=gw,
                )
            if tool_id in FEISHU_TOOL_IDS:
                return await handle_feishu_doc(
                    db,
                    params,
                    session_id=session_id,
                )
            if tool_id in OPENCLAW_RUNTIME_TOOL_IDS:
                if run_spec is None:
                    raise AgentFactoryException(
                        "RUNSPEC_REQUIRED",
                        f"{tool_id} requires RunSpec context",
                        status_code=500,
                    )
                from agent_factory.services.factory import get_model_gateway

                user_ctx = UserContext(
                    session_id=session_id or "",
                    user_id_hash=str(run_spec.user_id_hash or ""),
                    department=department,
                    permissions=tuple(caller_permissions or ()),
                )
                gw = model_gateway if model_gateway is not None else get_model_gateway()
                return await dispatch_openclaw_tool_async(
                    tool_id,
                    params,
                    db=db,
                    run_spec=run_spec,
                    session_id=session_id,
                    user_ctx=user_ctx,
                    model_gateway=gw,
                )
            return handler(params=params, retrieval_scopes=retrieval_scopes)

        row = await self._load_active_tool(db, tool_id)
        if row is None:
            raise AgentFactoryException(
                "TOOL_NOT_FOUND",
                f"Tool {tool_id} not found in registry",
                status_code=501,
            )
        self._validate_tool_input(params, row.input_schema)
        req = row.permission_required
        if caller_permissions is not None and isinstance(req, list) and req:
            for p in req:
                if not isinstance(p, str) or p not in caller_permissions:
                    raise AgentFactoryException(
                        "FORBIDDEN",
                        f"Missing permission {p!r} for tool {tool_id}",
                        status_code=403,
                    )
        impl = row.implementation if isinstance(row.implementation, dict) else {}
        impl_type = impl.get("type")
        if impl_type == "http_api":
            endpoint = impl.get("endpoint")
            if not isinstance(endpoint, str) or not endpoint.strip():
                raise AgentFactoryException(
                    "INVALID_TOOL_CONFIG",
                    "http_api tool missing implementation.endpoint",
                    status_code=500,
                )
            settings = get_settings()
            cb_cfg = build_http_tool_circuit_config(
                settings,
                row.rate_limit if isinstance(row.rate_limit, dict) else None,
            )
            scope = http_tool_circuit_scope(
                tool_id,
                department,
                per_department=settings.TOOL_HTTP_CIRCUIT_PER_DEPARTMENT,
            )
            redis = get_redis()
            await assert_http_tool_circuit_closed(redis, scope, cb_cfg)
            try:
                out = await self._invoke_http_api(
                    endpoint=endpoint.strip(),
                    params=params,
                    timeout_seconds=row.timeout_seconds,
                )
                await clear_http_tool_failures(redis, scope)
                return out
            except AgentFactoryException as exc:
                if failure_counts_toward_circuit(exc):
                    await record_http_tool_failure(redis, scope, cb_cfg)
                raise
        raise AgentFactoryException(
            "TOOL_NOT_IMPLEMENTED",
            f"Tool {tool_id} implementation type {impl_type!r} not supported",
            status_code=501,
        )

    def is_concurrency_safe(self, tool_id: str) -> bool:
        if tool_id in READ_ONLY_TOOL_IDS:
            return True
        if tool_id in (
            WORKSPACE_TOOL_IDS
            | MCP_TOOL_IDS
            | AGENT_TOOL_IDS
            | FEISHU_TOOL_IDS
            | OPENCLAW_RUNTIME_TOOL_IDS
        ):
            return False
        return tool_id in self._handlers

    def is_read_only(self, tool_id: str) -> bool:
        if tool_id in READ_ONLY_TOOL_IDS:
            return True
        if tool_id in (
            WORKSPACE_TOOL_IDS
            | MCP_TOOL_IDS
            | AGENT_TOOL_IDS
            | FEISHU_TOOL_IDS
            | OPENCLAW_RUNTIME_TOOL_IDS
        ):
            return False
        return tool_id in self._handlers

    def _check_allowlist(self, tool_id: str, allowed_tools: list[str]) -> None:
        if tool_id not in allowed_tools:
            raise AgentFactoryException(
                "TOOL_NOT_ALLOWED",
                f"Tool {tool_id} not in RunSpec allowed_tools",
                status_code=403,
            )

    def _validate_tool_input(
        self,
        params: dict[str, Any],
        input_schema: dict[str, Any] | None,
    ) -> None:
        """Lightweight runtime validation against JSON Schema subset (P0).

        Only checks ``type`` and ``required``; complex schemas fall through.
        """
        if not input_schema:
            return
        if input_schema.get("type") != "object":
            return
        required = input_schema.get("required", [])
        properties = input_schema.get("properties", {})
        for key in required:
            if key not in params:
                raise AgentFactoryException(
                    "INVALID_PARAMS",
                    f"Missing required parameter: {key}",
                    status_code=400,
                )
        for key, val in params.items():
            prop = properties.get(key)
            if not prop:
                continue
            ptype = prop.get("type")
            if ptype == "string" and not isinstance(val, str):
                raise AgentFactoryException(
                    "INVALID_PARAMS",
                    f"Parameter {key} must be a string",
                    status_code=400,
                )
            if ptype == "integer" and not isinstance(val, int):
                raise AgentFactoryException(
                    "INVALID_PARAMS",
                    f"Parameter {key} must be an integer",
                    status_code=400,
                )
            if ptype == "number" and not isinstance(val, (int, float)):
                raise AgentFactoryException(
                    "INVALID_PARAMS",
                    f"Parameter {key} must be a number",
                    status_code=400,
                )
            if ptype == "boolean" and not isinstance(val, bool):
                raise AgentFactoryException(
                    "INVALID_PARAMS",
                    f"Parameter {key} must be a boolean",
                    status_code=400,
                )
            if ptype == "array" and not isinstance(val, list):
                raise AgentFactoryException(
                    "INVALID_PARAMS",
                    f"Parameter {key} must be an array",
                    status_code=400,
                )
            if ptype == "object" and not isinstance(val, dict):
                raise AgentFactoryException(
                    "INVALID_PARAMS",
                    f"Parameter {key} must be an object",
                    status_code=400,
                )

    async def _load_active_tool(self, db: AsyncSession, tool_id: str) -> Tool | None:
        q = await db.execute(
            select(Tool).where(Tool.id == tool_id, Tool.status == "active")
        )
        return q.scalar_one_or_none()

    async def _invoke_http_api(
        self,
        *,
        endpoint: str,
        params: dict[str, Any],
        timeout_seconds: int | None,
    ) -> dict[str, Any]:
        """POST JSON to internal / partner HTTP API (allowlisted URLs only)."""
        settings = get_settings()
        prefixes = settings.internal_http_tool_url_prefixes
        if not prefixes:
            raise AgentFactoryException(
                "TOOL_HTTP_DISABLED",
                "Registry http_api tools require INTERNAL_HTTP_TOOL_URL_PREFIXES",
                status_code=503,
            )
        if not any(endpoint.startswith(p) for p in prefixes):
            raise AgentFactoryException(
                "TOOL_HTTP_FORBIDDEN",
                "Endpoint not under INTERNAL_HTTP_TOOL_URL_PREFIXES allowlist",
                status_code=403,
            )
        timeout = float(timeout_seconds or 30)
        headers = {"Content-Type": "application/json"}
        token = settings.INTERNAL_HTTP_TOOL_BEARER_TOKEN.strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(endpoint, json=params, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("Tool HTTP error: %s", exc)
            raise AgentFactoryException(
                "TOOL_HTTP_TRANSPORT",
                "HTTP transport failed",
                status_code=502,
            ) from exc
        if response.status_code >= 500:
            logger.warning(
                "Tool HTTP upstream %s: %s",
                response.status_code,
                (response.text or "")[:500],
            )
            raise AgentFactoryException(
                "TOOL_HTTP_UPSTREAM",
                "Upstream service error",
                status_code=502,
            )
        if response.status_code >= 400:
            logger.warning(
                "Tool HTTP client error %s: %s",
                response.status_code,
                (response.text or "")[:500],
            )
            raise AgentFactoryException(
                "TOOL_HTTP_CLIENT_ERROR",
                "Upstream rejected the request",
                status_code=400,
            )
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = response.json()
            except Exception:
                body = {"_raw": response.text}
            return body if isinstance(body, dict) else {"result": body}
        return {"text": response.text}

    def _handle_kb_search(
        self, params: dict[str, Any], retrieval_scopes: list[str]
    ) -> dict[str, Any]:
        scope = params.get("scope")
        if scope and scope not in retrieval_scopes:
            raise AgentFactoryException(
                "FORBIDDEN",
                f"Data domain {scope} not allowed",
                status_code=403,
            )
        query = params.get("query", "")
        # P0: stub; replace with real KB integration
        return {
            "results": [
                {
                    "id": "doc_001",
                    "title": f"Result for '{query}'",
                    "snippet": "(stub) Knowledge base search result...",
                }
            ],
            "total": 1,
        }

    async def _kb_upstream_search_async(
        self,
        *,
        params: dict[str, Any],
        retrieval_scopes: list[str],
        indexed_references: list[Any] | None = None,
        degradation_knobs: DegradationRunKnobs | None = None,
    ) -> dict[str, Any] | None:
        """Optional HTTP kb.search (external knowledge service)."""
        settings = get_settings()
        return await post_kb_search(
            settings,
            params=params,
            retrieval_scopes=retrieval_scopes,
            indexed_references=indexed_references,
            degradation_knobs=degradation_knobs,
        )

    async def _handle_kb_search_async(
        self,
        *,
        params: dict[str, Any],
        retrieval_scopes: list[str],
        indexed_references: list[Any] | None = None,
        degradation_knobs: DegradationRunKnobs | None = None,
    ) -> dict[str, Any]:
        """External KB when configured; else stub + query embedding (docs/10)."""
        settings = get_settings()
        upstream = await self._kb_upstream_search_async(
            params=params,
            retrieval_scopes=retrieval_scopes,
            indexed_references=indexed_references,
            degradation_knobs=degradation_knobs,
        )
        if upstream is not None:
            base: dict[str, Any] = dict(upstream)
        elif settings.KB_SEARCH_REQUIRE_UPSTREAM and (
            settings.KB_SEARCH_URL or ""
        ).strip():
            raise AgentFactoryException(
                "KB_SEARCH_UNAVAILABLE",
                "Knowledge base upstream unavailable",
                status_code=502,
            )
        else:
            base = self._handle_kb_search(
                params=params,
                retrieval_scopes=retrieval_scopes,
            )
        query = str(params.get("query", ""))
        try:
            broker = get_embedding_broker(settings)
            vec = await broker.embed_text(query)
            base = {**base, "query_embedding_dims": len(vec)}
        except Exception as exc:
            logger.warning("kb.search embedding batch failed: %s", exc)
        return base

    def _handle_risk_rule_check(
        self, params: dict[str, Any], retrieval_scopes: list[str]
    ) -> dict[str, Any]:
        """Sync path: built-in rules only."""
        _ = retrieval_scopes
        text = str(params.get("text") or params.get("clause") or "").strip()
        if not text:
            raise AgentFactoryException(
                "INVALID_PARAMS",
                "text or clause required",
                status_code=400,
            )
        return evaluate_rules(text)

    async def _handle_risk_rule_check_async(
        self,
        *,
        params: dict[str, Any],
        retrieval_scopes: list[str],
    ) -> dict[str, Any]:
        """Partner HTTP when configured; else built-in rule engine."""
        _ = retrieval_scopes
        text = str(params.get("text") or params.get("clause") or "").strip()
        if not text:
            raise AgentFactoryException(
                "INVALID_PARAMS",
                "text or clause required",
                status_code=400,
            )
        settings = get_settings()
        upstream = await post_risk_rule_check(settings, text=text)
        if upstream is not None:
            upstream.setdefault("engine", "partner_http")
            return upstream
        result = evaluate_rules(text)
        result["engine"] = "builtin"
        return result

    def _handle_doc_extract(
        self, params: dict[str, Any], retrieval_scopes: list[str]
    ) -> dict[str, Any]:
        file_id = params.get("file_id")
        if not file_id:
            raise AgentFactoryException(
                "INVALID_PARAMS", "file_id required", status_code=400
            )
        return {
            "file_id": file_id,
            "text": "(stub) Use validate_and_run_async for extracted text",
            "pages": 0,
        }

    async def _handle_doc_extract_async(
        self,
        db: AsyncSession,
        *,
        params: dict[str, Any],
        retrieval_scopes: list[str],
    ) -> dict[str, Any]:
        """Return text: prefer worker artifact; else inline ``extract_plain_text``."""
        _ = retrieval_scopes
        file_id = params.get("file_id")
        if not file_id:
            raise AgentFactoryException(
                "INVALID_PARAMS", "file_id required", status_code=400
            )
        fid = str(file_id)
        r = await db.execute(select(FileUpload).where(FileUpload.file_id == fid))
        row = r.scalar_one_or_none()
        if row is None:
            raise AgentFactoryException(
                "NOT_FOUND",
                "File not found",
                status_code=404,
            )
        if row.status != "extracted" or not row.extracted_text_path:
            if not row.storage_path:
                return {
                    "file_id": fid,
                    "text": (
                        "Original file not stored (upload may have failed); "
                        "cannot extract text."
                    ),
                    "pages": 0,
                }
            settings = get_settings()
            minio = MinioClient(settings)
            try:
                data = await minio.get_object(
                    settings.MINIO_BUCKET,
                    row.storage_path,
                )
            except Exception as exc:
                logger.warning(
                    "doc.extract minio get original failed: %s", exc
                )
                raise AgentFactoryException(
                    "DOC_EXTRACT_UNAVAILABLE",
                    "Failed to load uploaded file from storage",
                    status_code=502,
                ) from exc
            text = extract_plain_text(
                data,
                row.mime_type or "",
                file_name=row.file_name or "",
            )
            if not (text or "").strip():
                return {
                    "file_id": fid,
                    "text": (
                        "(empty) No body text extracted from this file "
                        "format or file is empty."
                    ),
                    "pages": 0,
                }
            extract_path = f"temp/{row.session_id}/extract_{row.file_id}.txt"
            try:
                raw_out = text.encode("utf-8")
                await minio.put_object(
                    bucket=settings.MINIO_BUCKET,
                    object_name=extract_path,
                    data=raw_out,
                    length=len(raw_out),
                    content_type="text/plain; charset=utf-8",
                )
                row.extracted_text_path = extract_path
                row.status = "extracted"
                await db.flush()
            except Exception:
                logger.exception(
                    "doc.extract persist to minio failed; returning inline"
                )
            return {"file_id": fid, "text": text, "pages": 1}

        settings = get_settings()
        minio = MinioClient(settings)
        try:
            raw = await minio.get_object(
                settings.MINIO_BUCKET,
                row.extracted_text_path,
            )
            text = raw.decode("utf-8")
        except Exception as exc:
            logger.warning("doc.extract read failed: %s", exc)
            raise AgentFactoryException(
                "DOC_EXTRACT_UNAVAILABLE",
                "Failed to load extracted document text",
                status_code=502,
            ) from exc
        return {"file_id": fid, "text": text, "pages": 1}

    def _handle_read_reference(
        self, params: dict[str, Any], retrieval_scopes: list[str]
    ) -> dict[str, Any]:
        """Sync stub; Runner uses ``validate_and_run_async`` with ``run_spec``."""
        _ = retrieval_scopes
        name = (params.get("name") or "").strip()
        if not name:
            raise AgentFactoryException(
                "INVALID_PARAMS", "name required", status_code=400
            )
        return {
            "name": name,
            "path": "",
            "content": "(stub) read_reference requires async RunSpec context",
        }

    async def _handle_read_reference_async(
        self,
        db: AsyncSession,
        *,
        run_spec: RunSpec,
        params: dict[str, Any],
        retrieval_scopes: list[str],
    ) -> dict[str, Any]:
        """Load on-demand reference text (docs/09)."""
        _ = retrieval_scopes
        name = (params.get("name") or "").strip()
        if not name:
            raise AgentFactoryException(
                "INVALID_PARAMS", "name required", status_code=400
            )
        sid = run_spec.skill_id
        sver = run_spec.skill_version
        if not sid or not sver:
            raise AgentFactoryException(
                "INTERNAL_ERROR",
                "RunSpec missing skill_id or skill_version",
                status_code=500,
            )
        q = await db.execute(
            select(Skill).where(Skill.id == sid, Skill.version == sver)
        )
        skill_row = q.scalar_one_or_none()
        if skill_row is None:
            raise AgentFactoryException(
                "NOT_FOUND",
                "Skill for RunSpec not found",
                status_code=404,
            )
        meta = skill_row.package_metadata
        pkg_meta: dict[str, Any] = meta if isinstance(meta, dict) else {}
        ref_files = pkg_meta.get("reference_files")
        ref_keys: frozenset[str] | None = None
        if isinstance(ref_files, dict):
            ref_keys = frozenset(str(k) for k in ref_files if isinstance(k, str))
        entry = find_lazy_reference_entry(
            run_spec.lazy_references,
            name,
            reference_file_keys=ref_keys,
        )
        if entry is None:
            raise AgentFactoryException(
                "REFERENCE_NOT_ALLOWED",
                "Reference not in RunSpec lazy_references",
                status_code=403,
            )
        text = resolve_reference_text(entry, pkg_meta)
        if text is None and skill_row.storage_path:
            settings = get_settings()
            minio = MinioClient(settings)
            tarball = await get_skill_bundle_bytes(
                minio, settings, skill_row.storage_path
            )
            verify_bundle_hash(tarball, skill_row.skill_package_hash)
            path = str(entry.get("path") or f"references/{name}.md")
            text = extract_text_from_tarball(tarball, path)
        if text is None:
            raise AgentFactoryException(
                "NOT_FOUND",
                "Reference content not available (inline or reference_files)",
                status_code=404,
            )
        path = str(entry.get("path") or f"references/{name}.md")
        try:
            verify_reference_manifest_hash(
                run_spec.skill_file_manifest, path, text
            )
        except ValueError as exc:
            raise AgentFactoryException(
                "REFERENCE_HASH_MISMATCH",
                "Skill file manifest hash mismatch for reference",
                status_code=409,
            ) from exc
        return {"name": name, "path": path, "content": text}

    def _handle_extended_tool(
        self, params: dict[str, Any], retrieval_scopes: list[str]
    ) -> dict[str, Any]:
        _ = params, retrieval_scopes
        raise AgentFactoryException(
            "ASYNC_REQUIRED",
            "Extended tools require validate_and_run_async",
            status_code=501,
        )

    def _handle_workspace_tool(
        self, params: dict[str, Any], retrieval_scopes: list[str]
    ) -> dict[str, Any]:
        return self._handle_extended_tool(params, retrieval_scopes)
