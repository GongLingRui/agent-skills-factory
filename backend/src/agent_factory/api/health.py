"""Liveness / readiness / metrics mount (metrics via instrumentator)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import get_settings
from agent_factory.infra.db import get_db_session
from agent_factory.services.readiness import run_all_readiness

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Process liveness (no dependency checks)."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """Dependency readiness for Kubernetes."""
    settings = get_settings()
    probes = await run_all_readiness(settings, db)
    failed = [p for p in probes if not p.ok]
    body = {
        "status": "ok" if not failed else "degraded",
        "checks": {p.name: {"ok": p.ok, "detail": p.detail} for p in probes},
    }
    if failed:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return body
