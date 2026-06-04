"""OpenClaw image / image_generate media tools."""

from __future__ import annotations

import base64
import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.core.workspace_sandbox import resolve_workspace_path, workspace_root
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.model_gateway import ModelGateway

logger = logging.getLogger(__name__)

MEDIA_TOOL_IDS: frozenset[str] = frozenset(
    {"media.image", "media.image_generate", "media.music_generate", "media.video_generate"}
)


def _require_media_enabled(settings: Settings) -> None:
    if not settings.MEDIA_TOOLS_ENABLED:
        raise AgentFactoryException(
            "MEDIA_DISABLED",
            "media tools disabled (set MEDIA_TOOLS_ENABLED=true)",
            status_code=503,
        )


def _read_image_as_data_url(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/png"
    b64 = base64.standard_b64encode(data).decode("ascii")
    return mime, f"data:{mime};base64,{b64}"


def _resolve_image_path(params: dict[str, Any], settings: Settings) -> Path:
    raw = (
        params.get("imagePath")
        or params.get("image_path")
        or params.get("path")
        or params.get("file_path")
    )
    if not isinstance(raw, str) or not raw.strip():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "imagePath (or path) is required",
            status_code=400,
        )
    if raw.strip().startswith("data:"):
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Use imagePath for files; data URLs not supported as path",
            status_code=400,
        )
    return resolve_workspace_path(raw.strip(), settings=settings, must_exist=True)


async def handle_media_image(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    model_gateway: ModelGateway | None,
    agent_model: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = db
    cfg = settings or get_settings()
    _require_media_enabled(cfg)
    fp = _resolve_image_path(params, cfg)
    if not fp.is_file():
        raise AgentFactoryException("NOT_FOUND", f"Image not found: {fp}", status_code=404)

    prompt = str(params.get("prompt") or params.get("question") or "Describe the image.").strip()
    mime, data_url = _read_image_as_data_url(fp)
    model = str(
        params.get("model")
        or agent_model
        or cfg.MEDIA_VISION_MODEL
        or "MiniMax-M2.7"
    ).strip()
    gateway = model_gateway or ModelGateway(cfg)

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]
    parts: list[str] = []
    async for chunk in gateway.chat(
        model=model,
        messages=messages,
        max_tokens=int(params.get("maxTokens") or 2000),
        temperature=0.2,
        tools=None,
        concurrency_class="interactive",
        queue_priority=2,
    ):
        for choice in chunk.choices:
            if choice.delta:
                parts.append(choice.delta)
    text = "".join(parts).strip()
    return {
        "path": str(fp),
        "mime": mime,
        "model": model,
        "prompt": prompt,
        "description": text,
    }


async def handle_media_image_generate(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = db
    cfg = settings or get_settings()
    _require_media_enabled(cfg)
    action = str(params.get("action") or "generate").strip().lower()

    if action == "status":
        return {
            "enabled": bool(cfg.MEDIA_IMAGE_GENERATE_URL or cfg.MEDIA_IMAGE_GENERATE_MODEL),
            "provider": cfg.MEDIA_IMAGE_GENERATE_PROVIDER,
        }

    if action == "list":
        root = workspace_root(cfg) / ".agent-factory" / "generated-images"
        root.mkdir(parents=True, exist_ok=True)
        files = sorted(root.glob("*.png"))[-20:]
        return {
            "images": [{"path": str(p.relative_to(workspace_root(cfg))), "name": p.name} for p in files],
        }

    prompt = str(params.get("prompt") or params.get("description") or "").strip()
    if not prompt:
        raise AgentFactoryException(
            "INVALID_PARAMS", "prompt is required", status_code=400
        )

    out_dir = workspace_root(cfg) / ".agent-factory" / "generated-images"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"gen_{uuid.uuid4().hex[:12]}.png"
    out_path = out_dir / out_name

    if cfg.MEDIA_IMAGE_GENERATE_URL:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                cfg.MEDIA_IMAGE_GENERATE_URL.strip(),
                json={"prompt": prompt, "model": cfg.MEDIA_IMAGE_GENERATE_MODEL or None},
                headers=(
                    {"Authorization": f"Bearer {cfg.MEDIA_IMAGE_GENERATE_API_KEY}"}
                    if cfg.MEDIA_IMAGE_GENERATE_API_KEY
                    else {}
                ),
            )
            if resp.status_code >= 400:
                raise AgentFactoryException(
                    "UPSTREAM_ERROR",
                    f"Image generation failed: HTTP {resp.status_code}",
                    status_code=502,
                )
            ctype = resp.headers.get("content-type", "")
            if "image" in ctype:
                out_path.write_bytes(resp.content)
            else:
                data = resp.json()
                b64 = data.get("image") or data.get("b64_json") or data.get("data")
                if isinstance(b64, str):
                    out_path.write_bytes(base64.standard_b64decode(b64))
                else:
                    raise AgentFactoryException(
                        "UPSTREAM_ERROR",
                        "Image generation response missing image data",
                        status_code=502,
                    )
    else:
        raise AgentFactoryException(
            "NOT_CONFIGURED",
            "Set MEDIA_IMAGE_GENERATE_URL for image generation",
            status_code=503,
        )

    rel = str(out_path.relative_to(workspace_root(cfg)))
    return {
        "status": "generated",
        "prompt": prompt,
        "path": rel,
        "format": "png",
    }


async def _media_generate_via_http(
    *,
    cfg: Settings,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    out_path: Path,
    binary_ext: str,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            url.strip(),
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )
        if resp.status_code >= 400:
            raise AgentFactoryException(
                "UPSTREAM_ERROR",
                f"Media generation failed: HTTP {resp.status_code}",
                status_code=502,
            )
        ctype = resp.headers.get("content-type", "")
        if binary_ext in ctype or "octet-stream" in ctype or binary_ext == "mp4":
            out_path.write_bytes(resp.content)
            return {"bytes": len(resp.content)}
        data = resp.json()
        for key in ("audio", "video", "data", "file", "b64_json", "base64"):
            val = data.get(key)
            if isinstance(val, str) and len(val) > 100:
                out_path.write_bytes(base64.standard_b64decode(val))
                return {"bytes": out_path.stat().st_size, "response": data}
        path_val = data.get("path")
        if isinstance(path_val, str):
            return {"remotePath": path_val, "response": data}
        raise AgentFactoryException(
            "UPSTREAM_ERROR",
            "Media generation response missing binary payload",
            status_code=502,
        )


async def handle_media_music_generate(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = db
    cfg = settings or get_settings()
    _require_media_enabled(cfg)
    action = str(params.get("action") or "generate").strip().lower()
    if action == "status":
        return {"enabled": bool(cfg.MEDIA_MUSIC_GENERATE_URL)}
    if action == "list":
        root = workspace_root(cfg) / ".agent-factory" / "generated-music"
        root.mkdir(parents=True, exist_ok=True)
        return {
            "files": [p.name for p in sorted(root.glob("*"))[-20:]],
        }
    prompt = str(params.get("prompt") or "").strip()
    lyrics = str(params.get("lyrics") or "").strip()
    if not prompt and not lyrics:
        raise AgentFactoryException(
            "INVALID_PARAMS", "prompt or lyrics required", status_code=400
        )
    if not cfg.MEDIA_MUSIC_GENERATE_URL:
        raise AgentFactoryException(
            "NOT_CONFIGURED",
            "Set MEDIA_MUSIC_GENERATE_URL for music generation",
            status_code=503,
        )
    out_dir = workspace_root(cfg) / ".agent-factory" / "generated-music"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"music_{uuid.uuid4().hex[:12]}.mp3"
    meta = await _media_generate_via_http(
        cfg=cfg,
        url=cfg.MEDIA_MUSIC_GENERATE_URL,
        api_key=cfg.MEDIA_MUSIC_GENERATE_API_KEY,
        payload={
            "prompt": prompt,
            "lyrics": lyrics or None,
            "model": cfg.MEDIA_MUSIC_GENERATE_MODEL or None,
        },
        out_path=out_path,
        binary_ext="audio",
    )
    rel = str(out_path.relative_to(workspace_root(cfg)))
    return {
        "status": "generated",
        "path": rel,
        "format": "mp3",
        "prompt": prompt,
        **meta,
    }


async def handle_media_video_generate(
    db: AsyncSession,
    params: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = db
    cfg = settings or get_settings()
    _require_media_enabled(cfg)
    action = str(params.get("action") or "generate").strip().lower()
    if action == "status":
        return {"enabled": bool(cfg.MEDIA_VIDEO_GENERATE_URL)}
    if action == "list":
        root = workspace_root(cfg) / ".agent-factory" / "generated-video"
        root.mkdir(parents=True, exist_ok=True)
        return {
            "files": [p.name for p in sorted(root.glob("*"))[-20:]],
        }
    prompt = str(params.get("prompt") or params.get("description") or "").strip()
    if not prompt:
        raise AgentFactoryException(
            "INVALID_PARAMS", "prompt is required", status_code=400
        )
    if not cfg.MEDIA_VIDEO_GENERATE_URL:
        raise AgentFactoryException(
            "NOT_CONFIGURED",
            "Set MEDIA_VIDEO_GENERATE_URL for video generation",
            status_code=503,
        )
    out_dir = workspace_root(cfg) / ".agent-factory" / "generated-video"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"video_{uuid.uuid4().hex[:12]}.mp4"
    meta = await _media_generate_via_http(
        cfg=cfg,
        url=cfg.MEDIA_VIDEO_GENERATE_URL,
        api_key=cfg.MEDIA_VIDEO_GENERATE_API_KEY,
        payload={
            "prompt": prompt,
            "model": cfg.MEDIA_VIDEO_GENERATE_MODEL or None,
            "duration": params.get("duration") or params.get("durationSeconds"),
        },
        out_path=out_path,
        binary_ext="mp4",
    )
    rel = str(out_path.relative_to(workspace_root(cfg)))
    return {
        "status": "generated",
        "path": rel,
        "format": "mp4",
        "prompt": prompt,
        **meta,
    }
