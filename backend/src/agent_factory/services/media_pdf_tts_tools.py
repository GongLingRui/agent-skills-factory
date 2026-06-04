"""OpenClaw pdf / tts media tools."""

from __future__ import annotations

import base64
import io
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.core.document_text_extract import extract_plain_text
from agent_factory.core.workspace_sandbox import resolve_workspace_path, workspace_root
from agent_factory.db.models.file_upload import FileUpload
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.model_gateway import ModelGateway

logger = logging.getLogger(__name__)

MEDIA_PDF_TTS_TOOL_IDS: frozenset[str] = frozenset({"media.pdf", "media.tts"})


def _require_media_enabled(settings: Settings) -> None:
    if not settings.MEDIA_TOOLS_ENABLED:
        raise AgentFactoryException(
            "MEDIA_DISABLED",
            "media tools disabled (set MEDIA_TOOLS_ENABLED=true)",
            status_code=503,
        )


def _parse_page_range(spec: str, total_pages: int) -> list[int]:
    """Parse OpenClaw-style page spec: ``1-5``, ``1,3,5-7`` (1-indexed)."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start = max(1, int(a.strip()))
            end = min(total_pages, int(b.strip()))
            out.extend(range(start, end + 1))
        else:
            p = int(part)
            if 1 <= p <= total_pages:
                out.append(p)
    return sorted(set(out))


def _extract_pdf_text(
    contents: bytes,
    *,
    pages: str | None = None,
    max_pages: int,
) -> tuple[str, int, list[int]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise AgentFactoryException(
            "PDF_UNAVAILABLE",
            "pypdf not installed",
            status_code=503,
        ) from exc
    reader = PdfReader(io.BytesIO(contents))
    total = len(reader.pages)
    if total == 0:
        return "", 0, []
    if pages:
        selected = _parse_page_range(pages, total)[:max_pages]
    else:
        selected = list(range(1, min(total, max_pages) + 1))
    parts: list[str] = []
    for p in selected:
        idx = p - 1
        if 0 <= idx < total:
            parts.append(reader.pages[idx].extract_text() or "")
    return "\n\n".join(parts).strip(), total, selected


async def _load_pdf_bytes(
    db: AsyncSession,
    params: dict[str, Any],
    settings: Settings,
) -> tuple[bytes, str]:
    file_id = str(params.get("file_id") or "").strip()
    raw_path = (
        params.get("pdf")
        or params.get("file_path")
        or (params.get("pdfs")[0] if isinstance(params.get("pdfs"), list) and params.get("pdfs") else None)
    )
    if file_id:
        q = await db.execute(select(FileUpload).where(FileUpload.file_id == file_id))
        row = q.scalar_one_or_none()
        if row is None:
            raise AgentFactoryException(
                "NOT_FOUND", f"file_id not found: {file_id}", status_code=404
            )
        if not row.storage_path:
            raise AgentFactoryException(
                "NOT_FOUND",
                "Uploaded file has no storage_path",
                status_code=404,
            )
        from agent_factory.infra.minio_client import MinioClient

        client = MinioClient(settings)
        data = await client.get_object(settings.MINIO_BUCKET, row.storage_path)
        name = row.file_name or "document.pdf"
        return data, name
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "pdf (path) or file_id is required",
            status_code=400,
        )
    fp = resolve_workspace_path(raw_path.strip(), settings=settings, must_exist=True)
    if fp.suffix.lower() != ".pdf":
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Path must be a .pdf file",
            status_code=400,
        )
    max_mb = int(params.get("maxBytesMb") or params.get("max_bytes_mb") or settings.MEDIA_PDF_MAX_BYTES_MB)
    max_bytes = max_mb * 1024 * 1024
    if fp.stat().st_size > max_bytes:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            f"PDF exceeds {max_mb}MB limit",
            status_code=400,
        )
    return fp.read_bytes(), fp.name


async def handle_media_pdf(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    model_gateway: ModelGateway | None = None,
    agent_model: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    _require_media_enabled(cfg)
    contents, name = await _load_pdf_bytes(db, params, cfg)
    pages_spec = str(params.get("pages") or "").strip() or None
    max_pages = int(cfg.MEDIA_PDF_MAX_PAGES)
    text, total_pages, selected = _extract_pdf_text(
        contents, pages=pages_spec, max_pages=max_pages
    )
    if not text:
        text = extract_plain_text(contents, "application/pdf", file_name=name) or ""
    prompt = str(params.get("prompt") or "Analyze this PDF document.").strip()
    result: dict[str, Any] = {
        "file": name,
        "totalPages": total_pages,
        "pagesExtracted": selected,
        "textLength": len(text),
        "extractedText": text[: int(cfg.MEDIA_PDF_MAX_TEXT_CHARS)],
        "truncated": len(text) > int(cfg.MEDIA_PDF_MAX_TEXT_CHARS),
    }
    if params.get("extractOnly") or params.get("extract_only"):
        return result

    gateway = model_gateway or ModelGateway(cfg)
    model = str(params.get("model") or agent_model or cfg.MEDIA_PDF_MODEL or "MiniMax-M2.7")
    body = text[: int(cfg.MEDIA_PDF_LLM_INPUT_CHARS)]
    messages = [
        {
            "role": "user",
            "content": f"{prompt}\n\n[PDF: {name}, pages {selected or 'all'}]\n\n{body}",
        }
    ]
    parts: list[str] = []
    async for chunk in gateway.chat(
        model=model,
        messages=messages,
        max_tokens=int(params.get("maxTokens") or 4000),
        temperature=0.2,
        tools=None,
        concurrency_class="interactive",
        queue_priority=2,
    ):
        for choice in chunk.choices:
            if choice.delta:
                parts.append(choice.delta)
    result["model"] = model
    result["prompt"] = prompt
    result["analysis"] = "".join(parts).strip()
    return result


async def handle_media_tts(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    session_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = db
    cfg = settings or get_settings()
    _require_media_enabled(cfg)
    text = str(params.get("text") or "").strip()
    if not text:
        raise AgentFactoryException(
            "INVALID_PARAMS", "text is required", status_code=400
        )
    if len(text) > int(cfg.MEDIA_TTS_MAX_CHARS):
        raise AgentFactoryException(
            "INVALID_PARAMS",
            f"text exceeds {cfg.MEDIA_TTS_MAX_CHARS} chars",
            status_code=400,
        )
    channel = str(params.get("channel") or "chat").strip()
    timeout_ms = params.get("timeoutMs") or params.get("timeout_ms")
    timeout = float(timeout_ms) / 1000.0 if timeout_ms else float(cfg.MEDIA_TTS_TIMEOUT_SECONDS)

    out_dir = workspace_root(cfg) / ".agent-factory" / "generated-audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"tts_{uuid.uuid4().hex[:12]}.mp3"
    out_path = out_dir / out_name

    if cfg.MEDIA_TTS_URL:
        payload: dict[str, Any] = {
            "text": text,
            "model": cfg.MEDIA_TTS_MODEL or None,
            "voice": cfg.MEDIA_TTS_VOICE or None,
            "channel": channel,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                cfg.MEDIA_TTS_URL.strip(),
                json=payload,
                headers=(
                    {"Authorization": f"Bearer {cfg.MEDIA_TTS_API_KEY}"}
                    if cfg.MEDIA_TTS_API_KEY
                    else {}
                ),
            )
            if resp.status_code >= 400:
                raise AgentFactoryException(
                    "UPSTREAM_ERROR",
                    f"TTS API HTTP {resp.status_code}",
                    status_code=502,
                )
            ctype = resp.headers.get("content-type", "")
            if "audio" in ctype or "octet-stream" in ctype:
                out_path.write_bytes(resp.content)
            else:
                data = resp.json()
                b64 = data.get("audio") or data.get("data") or data.get("b64_json")
                if isinstance(b64, str):
                    out_path.write_bytes(base64.standard_b64decode(b64))
                elif isinstance(data.get("audioPath"), str):
                    return {
                        "status": "ok",
                        "text": text,
                        "channel": channel,
                        "audioPath": data["audioPath"],
                        "provider": data.get("provider") or "http",
                    }
                else:
                    raise AgentFactoryException(
                        "UPSTREAM_ERROR",
                        "TTS response missing audio payload",
                        status_code=502,
                    )
        provider = "http"
    elif cfg.MEDIA_TTS_OPENAI_COMPAT and cfg.MEDIA_TTS_API_KEY:
        url = cfg.MEDIA_TTS_OPENAI_COMPAT.rstrip("/")
        if not url.endswith("/audio/speech"):
            url = f"{url}/audio/speech"
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                json={
                    "model": cfg.MEDIA_TTS_MODEL or "tts-1",
                    "input": text,
                    "voice": cfg.MEDIA_TTS_VOICE or "alloy",
                },
                headers={"Authorization": f"Bearer {cfg.MEDIA_TTS_API_KEY}"},
            )
            if resp.status_code >= 400:
                raise AgentFactoryException(
                    "UPSTREAM_ERROR",
                    f"OpenAI TTS HTTP {resp.status_code}",
                    status_code=502,
                )
            out_path.write_bytes(resp.content)
        provider = "openai_compat"
    else:
        raise AgentFactoryException(
            "NOT_CONFIGURED",
            "Set MEDIA_TTS_URL or MEDIA_TTS_OPENAI_COMPAT + MEDIA_TTS_API_KEY",
            status_code=503,
        )

    rel = str(out_path.relative_to(workspace_root(cfg)))
    ctx_audio: dict[str, Any] = {
        "audioPath": rel,
        "text": text,
        "channel": channel,
        "provider": provider,
    }
    if session_id:
        ctx_audio["sessionId"] = session_id

    return {
        "status": "ok",
        "spoken": f"(spoken) {text[:200]}",
        "text": text,
        "channel": channel,
        "audioPath": rel,
        "format": "mp3",
        "provider": provider,
        "media": {
            "mediaUrl": rel,
            "audioAsVoice": True,
        },
    }
