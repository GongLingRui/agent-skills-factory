"""Policy Registry CRUD with versioned rows (docs/19)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.db.models.policy import OrgPolicy, PlatformPolicy
from agent_factory.middleware.error_handler import AgentFactoryException


def _utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _next_version_platform(
    db: AsyncSession, lineage_id: str
) -> int:
    r = await db.execute(
        select(func.coalesce(func.max(PlatformPolicy.version), 0)).where(
            PlatformPolicy.lineage_id == lineage_id
        )
    )
    return int(r.scalar_one() or 0) + 1


async def _next_version_org(db: AsyncSession, lineage_id: str) -> int:
    r = await db.execute(
        select(func.coalesce(func.max(OrgPolicy.version), 0)).where(
            OrgPolicy.lineage_id == lineage_id
        )
    )
    return int(r.scalar_one() or 0) + 1


async def list_platform_policies(db: AsyncSession) -> list[dict[str, Any]]:
    q = await db.execute(
        select(PlatformPolicy).order_by(
            PlatformPolicy.lineage_id,
            PlatformPolicy.version.desc(),
        )
    )
    rows = q.scalars().all()
    return [
        {
            "id": p.lineage_id,
            "version": p.version,
            "prompt": p.prompt,
            "enabled": p.enabled,
            "created_at": p.created_at.isoformat() + "Z" if p.created_at else None,
            "updated_at": p.updated_at.isoformat() + "Z" if p.updated_at else None,
        }
        for p in rows
    ]


async def create_platform_policy_version(
    db: AsyncSession,
    *,
    lineage_id: str,
    prompt: str,
    enabled: bool,
) -> dict[str, Any]:
    ver = await _next_version_platform(db, lineage_id)
    now = _utc_naive()
    if enabled:
        await db.execute(
            update(PlatformPolicy)
            .where(PlatformPolicy.lineage_id == lineage_id)
            .values(enabled=False, updated_at=now)
        )
    row = PlatformPolicy(
        lineage_id=lineage_id,
        version=ver,
        prompt=prompt,
        enabled=enabled,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return {
        "id": lineage_id,
        "version": ver,
        "prompt": prompt,
        "enabled": enabled,
        "created_at": now.isoformat() + "Z",
        "updated_at": now.isoformat() + "Z",
    }


async def list_org_policies(
    db: AsyncSession, department: str
) -> list[dict[str, Any]]:
    q = await db.execute(
        select(OrgPolicy)
        .where(OrgPolicy.department == department)
        .order_by(OrgPolicy.lineage_id, OrgPolicy.version.desc())
    )
    rows = q.scalars().all()
    return [
        {
            "id": p.lineage_id,
            "version": p.version,
            "prompt": p.prompt,
            "enabled": p.enabled,
            "created_at": p.created_at.isoformat() + "Z" if p.created_at else None,
            "updated_at": p.updated_at.isoformat() + "Z" if p.updated_at else None,
        }
        for p in rows
    ]


async def create_org_policy_version(
    db: AsyncSession,
    *,
    lineage_id: str,
    department: str,
    prompt: str,
    enabled: bool,
) -> dict[str, Any]:
    ver = await _next_version_org(db, lineage_id)
    now = _utc_naive()
    if enabled:
        await db.execute(
            update(OrgPolicy)
            .where(
                OrgPolicy.lineage_id == lineage_id,
                OrgPolicy.department == department,
            )
            .values(enabled=False, updated_at=now)
        )
    row = OrgPolicy(
        lineage_id=lineage_id,
        version=ver,
        department=department,
        prompt=prompt,
        enabled=enabled,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return {
        "id": lineage_id,
        "version": ver,
        "prompt": prompt,
        "enabled": enabled,
        "created_at": now.isoformat() + "Z",
        "updated_at": now.isoformat() + "Z",
    }


async def assert_org_lineage_department(
    db: AsyncSession,
    *,
    lineage_id: str,
    department: str,
) -> None:
    """PUT org policy must target existing lineage in the same department."""
    r = await db.execute(
        select(OrgPolicy.department)
        .where(OrgPolicy.lineage_id == lineage_id)
        .limit(1)
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise AgentFactoryException(
            "NOT_FOUND",
            f"Unknown org policy lineage: {lineage_id}",
            status_code=404,
        )
    if row != department:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "policy lineage belongs to a different department",
            status_code=400,
        )
