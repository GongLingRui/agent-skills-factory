"""Readiness probes for /ready (PostgreSQL, Redis, MinIO, optional model)."""

from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings


@dataclass
class ProbeResult:
    name: str
    ok: bool
    detail: str


async def check_postgres(session: AsyncSession) -> ProbeResult:
    try:
        await session.execute(text("SELECT 1"))
        return ProbeResult("postgresql", True, "ok")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult("postgresql", False, str(exc)[:200])


async def check_redis(redis_url: str) -> ProbeResult:
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(redis_url, decode_responses=True)
        try:
            pong = await client.ping()
            ok = pong is True
            return ProbeResult("redis", ok, "ok" if ok else "unexpected_pong")
        finally:
            await client.aclose()
    except Exception as exc:  # noqa: BLE001
        return ProbeResult("redis", False, str(exc)[:200])


async def check_minio(settings: Settings) -> ProbeResult:
    if not settings.READY_CHECK_MINIO:
        return ProbeResult("minio", True, "skipped")
    if not settings.MINIO_ACCESS_KEY or not settings.MINIO_SECRET_KEY:
        return ProbeResult("minio", True, "skipped_no_credentials")
    try:
        from urllib.parse import urlparse

        from minio import Minio

        raw = settings.MINIO_ENDPOINT
        if "://" in raw:
            parsed = urlparse(raw)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 9000)
            secure = parsed.scheme == "https"
        else:
            parts = raw.split(":")
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 9000
            secure = settings.MINIO_USE_SSL

        client = Minio(
            f"{host}:{port}",
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=secure,
        )
        exists = client.bucket_exists(settings.MINIO_BUCKET)
        if not exists:
            return ProbeResult(
                "minio",
                False,
                f"bucket_missing:{settings.MINIO_BUCKET}",
            )
        return ProbeResult("minio", True, "ok")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult("minio", False, str(exc)[:200])


async def check_model_gateway(settings: Settings) -> ProbeResult:
    if not settings.READY_CHECK_MODEL_GATEWAY:
        return ProbeResult("model_gateway", True, "skipped")
    path = Path(settings.MODELS_CONFIG_PATH)
    if not path.is_file():
        return ProbeResult("model_gateway", False, f"config_missing:{path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        models = data.get("models") or {}
        if not models:
            return ProbeResult("model_gateway", True, "no_models_configured")
        first = next(iter(models.values()))
        health_url = first.get("health_endpoint")
        if not health_url:
            return ProbeResult("model_gateway", True, "no_health_endpoint")
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(health_url)
            if 200 <= r.status_code < 300:
                return ProbeResult("model_gateway", True, "ok")
            return ProbeResult(
                "model_gateway",
                False,
                f"http_{r.status_code}",
            )
    except Exception as exc:  # noqa: BLE001
        return ProbeResult("model_gateway", False, str(exc)[:200])


async def run_all_readiness(
    settings: Settings,
    db_session: AsyncSession,
) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    results.append(await check_postgres(db_session))
    results.append(await check_redis(settings.REDIS_URL))
    results.append(await check_minio(settings))
    results.append(await check_model_gateway(settings))
    return results
