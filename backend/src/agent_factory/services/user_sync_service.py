"""Directory snapshot + overlay merge (UNFINISHED_WORK §3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.db.models.synced_department import SyncedDepartment
from agent_factory.db.models.synced_user import SyncedUser, UserRoleOverlay
from agent_factory.middleware.error_handler import AgentFactoryException


def _utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _roles_from_json(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    return []


async def list_users_page(
    db: AsyncSession,
    *,
    department: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(SyncedUser)
    if department:
        stmt = stmt.where(SyncedUser.department == department.strip())
    stmt = stmt.order_by(SyncedUser.user_id)
    q = await db.execute(stmt)
    all_rows = q.scalars().all()
    total = len(all_rows)
    start = (page - 1) * page_size
    slice_rows = all_rows[start : start + page_size]
    overlays = {}
    if slice_rows:
        ids = [u.user_id for u in slice_rows]
        qo = await db.execute(
            select(UserRoleOverlay).where(UserRoleOverlay.user_id.in_(ids))
        )
        for o in qo.scalars().all():
            overlays[o.user_id] = _roles_from_json(o.roles)
    items: list[dict[str, Any]] = []
    for u in slice_rows:
        portal = _roles_from_json(u.portal_roles)
        if u.user_id in overlays:
            merged = overlays[u.user_id]
        else:
            merged = list(portal)
        items.append(
            {
                "user_id": u.user_id,
                "name": u.display_name or "",
                "department": u.department or "",
                "roles": merged,
                "created_at": u.synced_at.isoformat() + "Z" if u.synced_at else None,
            }
        )
    return items, total


async def upsert_user_roles_overlay(
    db: AsyncSession,
    *,
    user_id: str,
    roles: list[str],
    reason: str | None,
    operator_id: str,
    actor_user_id: str,
) -> None:
    if user_id.strip() == actor_user_id.strip():
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "不允许为自己修改角色",
            status_code=400,
        )
    now = _utc_naive()
    q = await db.execute(
        select(UserRoleOverlay).where(UserRoleOverlay.user_id == user_id)
    )
    row = q.scalar_one_or_none()
    if row is None:
        row = UserRoleOverlay(
            user_id=user_id,
            roles=list(roles),
            reason=reason,
            operator_id=operator_id,
            updated_at=now,
        )
        db.add(row)
    else:
        row.roles = list(roles)
        row.reason = reason
        row.operator_id = operator_id
        row.updated_at = now
    await db.flush()


async def replace_directory_snapshot(
    db: AsyncSession,
    *,
    users: list[dict[str, Any]],
    departments: list[dict[str, Any]],
) -> dict[str, int]:
    """Upsert portal snapshot rows (webhook / cron)."""
    now = _utc_naive()
    for d in departments:
        code = str(d.get("code") or "").strip()
        if not code:
            continue
        q = await db.execute(
            select(SyncedDepartment).where(SyncedDepartment.code == code)
        )
        row = q.scalar_one_or_none()
        if row is None:
            row = SyncedDepartment(
                code=code,
                name=str(d.get("name") or "") or None,
                parent_code=(
                    str(d.get("parent") or "").strip() or None
                    if d.get("parent")
                    else None
                ),
                synced_at=now,
            )
            db.add(row)
        else:
            row.name = str(d.get("name") or "") or None
            pc = d.get("parent")
            row.parent_code = (
                str(pc).strip() if pc is not None and str(pc).strip() else None
            )
            row.synced_at = now
    for u in users:
        uid = str(u.get("user_id") or "").strip()
        if not uid:
            continue
        q = await db.execute(select(SyncedUser).where(SyncedUser.user_id == uid))
        row = q.scalar_one_or_none()
        roles = u.get("roles")
        pr = roles if isinstance(roles, list) else []
        if row is None:
            row = SyncedUser(
                user_id=uid,
                display_name=str(u.get("name") or "") or None,
                department=str(u.get("department") or "").strip() or None,
                portal_roles=pr,
                synced_at=now,
            )
            db.add(row)
        else:
            row.display_name = str(u.get("name") or "") or None
            row.department = str(u.get("department") or "").strip() or None
            row.portal_roles = pr
            row.synced_at = now
    await db.flush()
    return {"users": len(users), "departments": len(departments)}


async def list_departments_flat(db: AsyncSession) -> list[dict[str, Any]]:
    q = await db.execute(
        select(SyncedDepartment).order_by(SyncedDepartment.code)
    )
    rows = q.scalars().all()
    return [
        {
            "code": r.code,
            "name": r.name or r.code,
            "parent": r.parent_code,
        }
        for r in rows
    ]
