"""Feishu cloud document (docx) read/write tool — OpenClaw feishu_doc parity (core actions)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.feishu_client import FeishuClient

logger = logging.getLogger(__name__)

FEISHU_DOC_TOOL_ID = "feishu.doc"
FEISHU_TOOL_IDS: frozenset[str] = frozenset({FEISHU_DOC_TOOL_ID})

_BLOCK_TYPE_NAMES: dict[int, str] = {
    1: "Page",
    2: "Text",
    3: "Heading1",
    4: "Heading2",
    5: "Heading3",
    12: "Bullet",
    13: "Ordered",
    14: "Code",
    15: "Quote",
    17: "Todo",
    22: "Divider",
    27: "Image",
    31: "Table",
    32: "TableCell",
}
_STRUCTURED_BLOCK_TYPES = {14, 18, 21, 23, 27, 30, 31, 32}
_UNSUPPORTED_CHILDREN_TYPES = {31, 32}
_MAX_DESCENDANT_BLOCKS = 1000
_MAX_CONVERT_DEPTH = 8


def extract_doc_token(value: str) -> str:
    """Extract document_id from URL or raw token."""
    text = (value or "").strip()
    if not text:
        return ""
    m = re.search(r"/docx/([A-Za-z0-9_-]+)", text)
    if m:
        return m.group(1)
    return text


def _normalize_child_ids(children: Any) -> list[str]:
    if isinstance(children, list):
        return [str(c) for c in children if c]
    if isinstance(children, str) and children:
        return [children]
    return []


def normalize_converted_block_tree(
    blocks: list[dict[str, Any]],
    first_level_ids: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    if len(blocks) <= 1:
        root = (
            [blocks[0]["block_id"]]
            if blocks and isinstance(blocks[0].get("block_id"), str)
            else []
        )
        return blocks, root

    by_id: dict[str, dict[str, Any]] = {}
    original_order: dict[str, int] = {}
    for idx, block in enumerate(blocks):
        bid = block.get("block_id")
        if isinstance(bid, str):
            by_id[bid] = block
            original_order[bid] = idx

    child_ids: set[str] = set()
    for block in blocks:
        for cid in _normalize_child_ids(block.get("children")):
            child_ids.add(cid)

    inferred_top = [
        block["block_id"]
        for block in blocks
        if isinstance(block.get("block_id"), str)
        and block["block_id"] not in child_ids
        and (
            not isinstance(block.get("parent_id"), str)
            or block.get("parent_id") not in by_id
        )
    ]
    inferred_top.sort(key=lambda x: original_order.get(x, 0))

    root_ids = [
        bid
        for bid in (first_level_ids or inferred_top)
        if isinstance(bid, str) and bid in by_id
    ]
    seen: set[str] = set()
    root_ids = [x for x in root_ids if not (x in seen or seen.add(x))]

    ordered: list[dict[str, Any]] = []
    visited: set[str] = set()

    def visit(block_id: str) -> None:
        if block_id not in by_id or block_id in visited:
            return
        visited.add(block_id)
        block = by_id[block_id]
        ordered.append(block)
        for cid in _normalize_child_ids(block.get("children")):
            visit(cid)

    for rid in root_ids:
        visit(rid)
    for block in blocks:
        bid = block.get("block_id")
        if isinstance(bid, str):
            visit(bid)
        else:
            ordered.append(block)

    return ordered, root_ids


def clean_blocks_for_descendant(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for block in blocks:
        b = {k: v for k, v in block.items() if k != "parent_id"}
        if b.get("block_type") == 32 and isinstance(b.get("children"), str):
            b["children"] = [b["children"]]
        table = b.get("table")
        if b.get("block_type") == 31 and isinstance(table, dict):
            prop = table.get("property") if isinstance(table.get("property"), dict) else {}
            new_table: dict[str, Any] = {"property": {}}
            if prop.get("row_size") is not None:
                new_table["property"]["row_size"] = prop["row_size"]
            if prop.get("column_size") is not None:
                new_table["property"]["column_size"] = prop["column_size"]
            if isinstance(prop.get("column_width"), list) and prop["column_width"]:
                new_table["property"]["column_width"] = prop["column_width"]
            b["table"] = new_table
        if isinstance(b.get("children"), list):
            b["children"] = [c for c in b["children"] if c]
        cleaned.append(b)
    return cleaned


def _collect_descendant_subtree(
    block_map: dict[str, dict[str, Any]],
    root_id: str,
) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    visited: set[str] = set()

    def visit(block_id: str) -> None:
        if block_id in visited or block_id not in block_map:
            return
        visited.add(block_id)
        block = block_map[block_id]
        ordered.append(block)
        for cid in _normalize_child_ids(block.get("children")):
            visit(cid)

    visit(root_id)
    return ordered


def _strip_block_for_children_create(block: dict[str, Any]) -> dict[str, Any] | None:
    btype = int(block.get("block_type") or 0)
    if btype in _UNSUPPORTED_CHILDREN_TYPES:
        return None
    return {k: v for k, v in block.items() if k not in {"block_id", "parent_id", "children"}}


def split_markdown_by_headings(markdown: str) -> list[str]:
    lines = markdown.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in lines:
        if re.match(r"^(`{3,}|~{3,})", line):
            in_fence = not in_fence
        if not in_fence and re.match(r"^#{1,2}\s", line) and current:
            chunks.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        chunks.append("\n".join(current))
    return chunks or [markdown]


def split_markdown_by_size(markdown: str, max_chars: int) -> list[str]:
    if len(markdown) <= max_chars:
        return [markdown]
    lines = markdown.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    in_fence = False
    for line in lines:
        if re.match(r"^(`{3,}|~{3,})", line):
            in_fence = not in_fence
        line_len = len(line) + 1
        if current and current_len + line_len > max_chars and not in_fence:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    if len(chunks) > 1:
        return chunks
    mid = len(lines) // 2
    if mid <= 0 or mid >= len(lines):
        return [markdown]
    return ["\n".join(lines[:mid]), "\n".join(lines[mid:])]


class FeishuDocClient:
    """Async Feishu docx API client."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._auth = FeishuClient(self.settings)

    @property
    def api_base(self) -> str:
        return self._auth.api_base

    def doc_url(self, doc_token: str) -> str:
        host = "feishu.cn"
        if "larksuite.com" in self.api_base:
            host = "larksuite.com"
        return f"https://{host}/docx/{doc_token}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = await self._auth._auth_headers()
        url = f"{self.api_base}{path}"
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.request(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params,
            )
            try:
                data = resp.json()
            except Exception:
                data = {}
        if resp.status_code >= 400:
            detail = data.get("msg") or data.get("error") or resp.text[:500]
            logger.warning(
                "feishu_doc_api_http_error status=%s path=%s detail=%s",
                resp.status_code,
                path,
                detail,
            )
            raise AgentFactoryException(
                "FEISHU_DOC_API_ERROR",
                f"HTTP {resp.status_code}: {detail}",
                status_code=502,
            )
        code = int(data.get("code", -1))
        if code != 0:
            raise AgentFactoryException(
                "FEISHU_DOC_API_ERROR",
                str(data.get("msg") or data),
                status_code=502,
            )
        payload = data.get("data")
        return payload if isinstance(payload, dict) else {"raw": payload}

    async def convert_markdown(self, markdown: str, depth: int = 0) -> dict[str, Any]:
        try:
            return await self._request(
                "POST",
                "/open-apis/docx/v1/documents/blocks/convert",
                json_body={"content_type": "markdown", "content": markdown},
            )
        except AgentFactoryException:
            if depth >= _MAX_CONVERT_DEPTH or len(markdown) < 2:
                raise
            target = max(256, len(markdown) // 2)
            parts = split_markdown_by_size(markdown, target)
            if len(parts) <= 1:
                raise
            blocks: list[dict[str, Any]] = []
            root_ids: list[str] = []
            for part in parts:
                converted = await self.convert_markdown(part, depth + 1)
                blocks.extend(converted.get("blocks") or [])
                root_ids.extend(converted.get("first_level_block_ids") or [])
            return {"blocks": blocks, "first_level_block_ids": root_ids}

    async def chunked_convert_markdown(self, markdown: str) -> dict[str, Any]:
        """Convert markdown in heading-sized chunks (do not merge inserts)."""
        all_blocks: list[dict[str, Any]] = []
        all_roots: list[str] = []
        for chunk in split_markdown_by_headings(markdown):
            body = chunk.strip()
            if not body:
                continue
            converted = await self.convert_markdown(body)
            blocks = converted.get("blocks") or []
            roots = converted.get("first_level_block_ids") or []
            ordered, root_ids = normalize_converted_block_tree(blocks, roots)
            all_blocks.extend(ordered)
            all_roots.extend(root_ids)
        return {"blocks": all_blocks, "first_level_block_ids": all_roots}

    async def insert_descendant(
        self,
        doc_token: str,
        blocks: list[dict[str, Any]],
        first_level_ids: list[str],
        *,
        parent_block_id: str | None = None,
        index: int = -1,
    ) -> list[dict[str, Any]]:
        descendants = clean_blocks_for_descendant(blocks)
        if not descendants:
            return []
        parent = parent_block_id or doc_token
        body: dict[str, Any] = {
            "children_id": first_level_ids,
            "descendants": descendants,
        }
        if index >= 0:
            body["index"] = index
        data = await self._request(
            "POST",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{parent}/descendant",
            json_body=body,
        )
        children = data.get("children")
        return children if isinstance(children, list) else []

    async def insert_children_sequential(
        self,
        doc_token: str,
        blocks: list[dict[str, Any]],
        first_level_ids: list[str],
        *,
        parent_block_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fallback: insert top-level blocks one-by-one (no tables)."""
        parent = parent_block_id or doc_token
        block_map = {
            str(b["block_id"]): b
            for b in blocks
            if isinstance(b.get("block_id"), str)
        }
        inserted: list[dict[str, Any]] = []
        for root_id in first_level_ids:
            block = block_map.get(root_id)
            if not block:
                continue
            payload = _strip_block_for_children_create(block)
            if payload is None:
                raise AgentFactoryException(
                    "FEISHU_DOC_TABLE_UNSUPPORTED",
                    "Table blocks require descendant insert; sequential fallback cannot apply",
                    status_code=502,
                )
            data = await self._request(
                "POST",
                f"/open-apis/docx/v1/documents/{doc_token}/blocks/{parent}/children",
                json_body={"children": [payload], "index": -1},
            )
            children = data.get("children")
            if isinstance(children, list):
                inserted.extend(children)
        return inserted

    async def _insert_blocks_with_fallback(
        self,
        doc_token: str,
        blocks: list[dict[str, Any]],
        first_level_ids: list[str],
    ) -> list[dict[str, Any]]:
        block_map = {
            str(b["block_id"]): b
            for b in blocks
            if isinstance(b.get("block_id"), str)
        }
        all_inserted: list[dict[str, Any]] = []
        batch_blocks: list[dict[str, Any]] = []
        batch_roots: list[str] = []
        used_ids: set[str] = set()

        async def flush_batch() -> None:
            nonlocal batch_blocks, batch_roots, all_inserted
            if not batch_blocks:
                return
            try:
                children = await self.insert_descendant(
                    doc_token, batch_blocks, batch_roots
                )
            except AgentFactoryException:
                logger.warning(
                    "feishu_doc_descendant_failed roots=%s trying_sequential",
                    batch_roots,
                )
                children = await self.insert_children_sequential(
                    doc_token, batch_blocks, batch_roots
                )
            all_inserted.extend(children)
            batch_blocks = []
            batch_roots = []

        for root_id in first_level_ids:
            subtree = _collect_descendant_subtree(block_map, root_id)
            new_blocks = [
                b
                for b in subtree
                if isinstance(b.get("block_id"), str)
                and b["block_id"] not in used_ids
            ]
            if len(new_blocks) > _MAX_DESCENDANT_BLOCKS:
                raise AgentFactoryException(
                    "FEISHU_DOC_TOO_LARGE",
                    f"Section {root_id} exceeds {_MAX_DESCENDANT_BLOCKS} blocks",
                    status_code=400,
                )
            if (
                batch_blocks
                and len(batch_blocks) + len(new_blocks) > _MAX_DESCENDANT_BLOCKS
            ):
                await flush_batch()
            batch_roots.append(root_id)
            for b in new_blocks:
                bid = str(b["block_id"])
                used_ids.add(bid)
                batch_blocks.append(b)
        await flush_batch()
        return all_inserted

    async def _insert_markdown_chunks(
        self,
        doc_token: str,
        markdown: str,
    ) -> tuple[int, list[dict[str, Any]]]:
        """Convert and insert markdown chunk-by-chunk to avoid temp block_id collisions."""
        total_blocks = 0
        all_inserted: list[dict[str, Any]] = []
        chunks = split_markdown_by_headings(markdown) or [markdown]
        for chunk in chunks:
            body = chunk.strip()
            if not body:
                continue
            converted = await self.convert_markdown(body)
            blocks = converted.get("blocks") or []
            roots = converted.get("first_level_block_ids") or []
            if not blocks:
                continue
            ordered, root_ids = normalize_converted_block_tree(blocks, roots)
            inserted = await self._insert_blocks_with_fallback(
                doc_token, ordered, root_ids
            )
            total_blocks += len(blocks)
            all_inserted.extend(inserted)
        return total_blocks, all_inserted

    async def clear_document(self, doc_token: str) -> int:
        data = await self._request(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks",
            params={"page_size": 500},
        )
        items = data.get("items") or []
        child_count = sum(
            1
            for b in items
            if isinstance(b, dict)
            and b.get("parent_id") == doc_token
            and b.get("block_type") != 1
        )
        if child_count <= 0:
            return 0
        await self._request(
            "DELETE",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks/{doc_token}/children/batch_delete",
            json_body={"start_index": 0, "end_index": child_count},
        )
        return child_count

    async def read_document(self, doc_token: str) -> dict[str, Any]:
        content_data, info_data, blocks_data = await self._gather(
            self._request(
                "GET",
                f"/open-apis/docx/v1/documents/{doc_token}/raw_content",
            ),
            self._request("GET", f"/open-apis/docx/v1/documents/{doc_token}"),
            self._request(
                "GET",
                f"/open-apis/docx/v1/documents/{doc_token}/blocks",
                params={"page_size": 500},
            ),
        )
        blocks = blocks_data.get("items") or []
        block_counts: dict[str, int] = {}
        structured: list[str] = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            btype = int(b.get("block_type") or 0)
            name = _BLOCK_TYPE_NAMES.get(btype, f"type_{btype}")
            block_counts[name] = block_counts.get(name, 0) + 1
            if btype in _STRUCTURED_BLOCK_TYPES and name not in structured:
                structured.append(name)
        hint = None
        if structured:
            hint = (
                f"Document contains {', '.join(structured)} not fully represented in plain "
                'text. Use feishu.doc action "list_blocks" for structure.'
            )
        doc = info_data.get("document") or {}
        return {
            "title": doc.get("title"),
            "content": content_data.get("content"),
            "revision_id": doc.get("revision_id"),
            "block_count": len(blocks),
            "block_types": block_counts,
            **({"hint": hint} if hint else {}),
        }

    async def list_blocks(self, doc_token: str) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_token}/blocks",
            params={"page_size": 500},
        )
        items = data.get("items") or []
        return {"blocks": items, "total": len(items)}

    async def create_document(
        self,
        title: str,
        *,
        folder_token: str | None = None,
        requester_open_id: str | None = None,
        grant_to_requester: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title}
        if folder_token:
            body["folder_token"] = folder_token
        data = await self._request(
            "POST",
            "/open-apis/docx/v1/documents",
            json_body=body,
        )
        doc = data.get("document") or {}
        doc_token = str(doc.get("document_id") or "")
        if not doc_token:
            raise AgentFactoryException(
                "FEISHU_DOC_CREATE_FAILED",
                "Document created but document_id missing",
                status_code=502,
            )
        result: dict[str, Any] = {
            "document_id": doc_token,
            "doc_token": doc_token,
            "title": doc.get("title") or title,
            "url": self.doc_url(doc_token),
        }
        if grant_to_requester:
            oid = (requester_open_id or "").strip()
            if not oid:
                result["requester_permission_skipped_reason"] = (
                    "feishu_open_id unavailable in session context"
                )
            else:
                try:
                    await self._request(
                        "POST",
                        f"/open-apis/drive/v1/permissions/{doc_token}/members",
                        params={"type": "docx", "need_notification": "false"},
                        json_body={
                            "member_type": "openid",
                            "member_id": oid,
                            "perm": "edit",
                        },
                    )
                    result["requester_permission_added"] = True
                    result["requester_open_id"] = oid
                except AgentFactoryException as exc:
                    result["requester_permission_error"] = exc.message
        return result

    async def write_document(self, doc_token: str, markdown: str) -> dict[str, Any]:
        deleted = await self.clear_document(doc_token)
        total_blocks, inserted = await self._insert_markdown_chunks(doc_token, markdown)
        return {
            "success": True,
            "blocks_deleted": deleted,
            "blocks_added": total_blocks,
            "block_ids": [
                b.get("block_id") for b in inserted if isinstance(b, dict) and b.get("block_id")
            ],
            "url": self.doc_url(doc_token),
        }

    async def append_document(self, doc_token: str, markdown: str) -> dict[str, Any]:
        total_blocks, inserted = await self._insert_markdown_chunks(doc_token, markdown)
        if total_blocks <= 0:
            raise AgentFactoryException(
                "INVALID_PARAMS", "Content is empty after conversion", status_code=400
            )
        return {
            "success": True,
            "blocks_added": total_blocks,
            "block_ids": [
                b.get("block_id") for b in inserted if isinstance(b, dict) and b.get("block_id")
            ],
            "url": self.doc_url(doc_token),
        }

    @staticmethod
    async def _gather(*coros: Any) -> tuple[dict[str, Any], ...]:
        import asyncio

        results = await asyncio.gather(*coros)
        return tuple(r if isinstance(r, dict) else {} for r in results)


async def _resolve_feishu_open_id(
    db: AsyncSession,
    session_id: str | None,
) -> str | None:
    if not session_id:
        return None
    q = await db.execute(
        select(ChatSession.runtime_context).where(ChatSession.session_id == session_id)
    )
    ctx = q.scalar_one_or_none()
    if not isinstance(ctx, dict):
        return None
    oid = ctx.get("feishu_open_id")
    return str(oid).strip() if oid else None


def build_agents_markdown_for_feishu_doc(agents: list[dict[str, str]]) -> str:
    """Format agent.list rows as Feishu-doc-friendly markdown."""
    lines = [
        "# Agent Factory 可用 Agents",
        "",
        f"共 **{len(agents)}** 个 active Agent（自动生成）。",
        "",
        "| ID | 名称 | 描述 |",
        "| --- | --- | --- |",
    ]
    for ag in agents:
        aid = str(ag.get("id") or "").strip()
        name = str(ag.get("name") or aid).replace("|", "\\|").replace("\n", " ")
        desc = str(ag.get("description") or "").replace("|", "\\|").replace("\n", " ")[:200]
        lines.append(f"| {aid} | {name} | {desc or '—'} |")
    return "\n".join(lines)


async def export_agents_to_feishu_document(
    db: AsyncSession,
    *,
    requester_open_id: str,
    title: str = "Agent Factory 可用 Agents",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """List active agents and write them into a new Feishu doc (no LLM multi-turn)."""
    from agent_factory.services.agent_spawn_tool import handle_agent_list

    cfg = settings or get_settings()
    if not cfg.FEISHU_ENABLED:
        raise AgentFactoryException(
            "FEISHU_NOT_CONFIGURED",
            "Feishu integration is disabled",
            status_code=503,
        )
    listed = await handle_agent_list(db, {}, settings=cfg)
    agents = listed.get("agents") or []
    if not isinstance(agents, list):
        agents = []
    markdown = build_agents_markdown_for_feishu_doc(
        [a for a in agents if isinstance(a, dict)]
    )
    client = FeishuDocClient(cfg)
    doc = await client.create_document(
        title,
        requester_open_id=requester_open_id or None,
        grant_to_requester=True,
    )
    token = str(doc.get("doc_token") or doc.get("document_id") or "")
    write_result = await client.write_document(token, markdown)
    return {
        **doc,
        **write_result,
        "agent_count": len(agents),
        "title": title,
    }


async def handle_feishu_doc(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    session_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    if not cfg.FEISHU_ENABLED or not cfg.FEISHU_APP_ID.strip():
        raise AgentFactoryException(
            "FEISHU_NOT_CONFIGURED",
            "Feishu integration is disabled or missing credentials",
            status_code=503,
        )

    action = str(params.get("action") or "").strip().lower()
    client = FeishuDocClient(cfg)
    requester_open_id = await _resolve_feishu_open_id(db, session_id)

    if action == "read":
        token = extract_doc_token(str(params.get("doc_token") or ""))
        if not token:
            raise AgentFactoryException("INVALID_PARAMS", "doc_token required", status_code=400)
        return await client.read_document(token)

    if action == "list_blocks":
        token = extract_doc_token(str(params.get("doc_token") or ""))
        if not token:
            raise AgentFactoryException("INVALID_PARAMS", "doc_token required", status_code=400)
        return await client.list_blocks(token)

    if action == "create":
        title = str(params.get("title") or "").strip()
        if not title:
            raise AgentFactoryException("INVALID_PARAMS", "title required", status_code=400)
        folder = str(params.get("folder_token") or "").strip() or None
        grant = params.get("grant_to_requester", True) is not False
        return await client.create_document(
            title,
            folder_token=folder,
            requester_open_id=requester_open_id,
            grant_to_requester=grant,
        )

    if action == "write":
        token = extract_doc_token(str(params.get("doc_token") or ""))
        content = str(params.get("content") or "")
        if not token:
            raise AgentFactoryException("INVALID_PARAMS", "doc_token required", status_code=400)
        return await client.write_document(token, content)

    if action == "append":
        token = extract_doc_token(str(params.get("doc_token") or ""))
        content = str(params.get("content") or "")
        if not token:
            raise AgentFactoryException("INVALID_PARAMS", "doc_token required", status_code=400)
        return await client.append_document(token, content)

    raise AgentFactoryException(
        "INVALID_PARAMS",
        f"Unsupported feishu.doc action: {action!r}. "
        "Use read, write, append, create, or list_blocks.",
        status_code=400,
    )
