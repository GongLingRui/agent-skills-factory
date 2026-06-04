"""Persist large tool results to MinIO and load them back."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_factory.core.context_memory import ContextMemorySettings
from agent_factory.infra.minio_client import MinioClient

logger = logging.getLogger(__name__)

_TOOL_RESULT_STUB_PREFIX = '{"_tool_result_stub": true'


def should_persist_tool_result(content: str, cfg: ContextMemorySettings) -> bool:
    """True when *content* exceeds the per-tool-result character budget."""
    return len(content) > cfg.tool_result_max_chars


def make_tool_result_stub(*, minio_path: str, preview: str) -> str:
    """Build a JSON stub referencing the persisted result."""
    obj = {
        "_tool_result_stub": True,
        "minio_path": minio_path,
        "truncated_preview": preview,
    }
    return json.dumps(obj, ensure_ascii=False)


def is_tool_result_stub(content: str) -> bool:
    """Fast check whether *content* is a stub JSON."""
    if not isinstance(content, str) or not content.startswith("{"):
        return False
    return '{"_tool_result_stub":' in content or '{"_tool_result_stub" :' in content


def parse_tool_result_stub(content: str) -> dict[str, Any] | None:
    """Parse a stub JSON; return None if invalid."""
    if not is_tool_result_stub(content):
        return None
    try:
        obj = json.loads(content)
        if obj.get("_tool_result_stub") is True and isinstance(obj.get("minio_path"), str):
            return obj
    except json.JSONDecodeError:
        pass
    return None


def build_minio_path(bucket: str, run_id: str, turn: int, tool_call_id: str) -> str:
    """Deterministic object name for a tool result."""
    safe_id = tool_call_id.replace("/", "_").replace("\x00", "")
    return f"{bucket}/tool_results/{run_id}/{turn}/{safe_id}.json"


async def persist_large_tool_result(
    minio: MinioClient,
    bucket: str,
    run_id: str,
    turn: int,
    tool_call_id: str,
    content: str,
) -> str:
    """Write *content* to MinIO and return the minio_path."""
    path = build_minio_path(bucket, run_id, turn, tool_call_id)
    data = content.encode("utf-8")
    await minio.put_object(
        bucket=bucket,
        object_name=path,
        data=data,
        length=len(data),
        content_type="application/json; charset=utf-8",
    )
    logger.info("tool_result_persisted", extra={"path": path, "bytes": len(data)})
    return path


async def load_tool_result_from_persistence(
    minio: MinioClient,
    bucket: str,
    minio_path: str,
) -> str:
    """Read back a persisted tool result from MinIO."""
    try:
        data = await minio.get_object(bucket=bucket, object_name=minio_path)
        return data.decode("utf-8")
    except Exception:
        logger.exception("tool_result_load_failed", extra={"path": minio_path})
        return "[工具结果加载失败：无法从对象存储读取]"
