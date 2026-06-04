"""Tool Registry routes (docs/09, docs/19)."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.api.deps_admin import (
    RegistryAuth,
    SessionOrOperatorAuth,
    require_session_or_admin_operator,
    require_tool_admin,
)
from agent_factory.config import get_settings
from agent_factory.db.models.tool import Tool
from agent_factory.db.models.tool_approval_log import ToolApprovalLog
from agent_factory.infra.db import get_db_session
from agent_factory.middleware.error_handler import AgentFactoryException

router = APIRouter()


def _tool_operator_id(auth: RegistryAuth) -> str:
    if auth == "bearer":
        return "bearer_admin"
    return auth.user_id_hash


class ToolCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    version: str | None = Field(None, max_length=32)
    name: str | None = Field(None, max_length=128)
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    permission_required: list[str] = []
    timeout_seconds: int | None = Field(None, ge=1)
    rate_limit: dict[str, int] | None = None
    implementation: dict[str, Any] | None = None


class ToolUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    permission_required: list[str] | None = None
    timeout_seconds: int | None = Field(None, ge=1)
    rate_limit: dict[str, int] | None = None
    implementation: dict[str, Any] | None = None
    status: str | None = Field(
        None,
        pattern="^(active|disabled|pending_approval)$",
    )


@router.post("")
async def create_tool(
    body: ToolCreate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[RegistryAuth, Depends(require_tool_admin)],
) -> dict[str, Any]:
    """Register a new Tool."""
    existing = await db.execute(select(Tool).where(Tool.id == body.id))
    if existing.scalar_one_or_none():
        raise AgentFactoryException(
            "CONFLICT",
            f"Tool {body.id} already exists",
            status_code=409,
        )
    row = Tool(
        id=body.id,
        version=body.version,
        name=body.name,
        description=body.description,
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        permission_required=body.permission_required,
        timeout_seconds=body.timeout_seconds,
        rate_limit=body.rate_limit,
        implementation=body.implementation,
        status=(
            "pending_approval"
            if get_settings().TOOL_DUAL_SIGN_ENABLED
            else "active"
        ),
        submitted_by_operator_id=(
            _tool_operator_id(_auth)
            if get_settings().TOOL_DUAL_SIGN_ENABLED
            else None
        ),
        approved_by_operator_id=None,
    )
    db.add(row)
    await db.flush()
    return {"id": row.id, "status": row.status}


@router.get("")
async def list_tools(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[SessionOrOperatorAuth, Depends(require_session_or_admin_operator)],
    status: str | None = None,
) -> dict[str, Any]:
    """List tools (default active only)."""
    stmt = select(Tool)
    if status:
        stmt = stmt.where(Tool.status == status)
    else:
        stmt = stmt.where(Tool.status == "active")
    stmt = stmt.order_by(Tool.id)
    q = await db.execute(stmt)
    rows = q.scalars().all()
    return {
        "tools": [
            {
                "id": t.id,
                "version": t.version,
                "name": t.name,
                "description": t.description,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ]
    }


@router.get("/{tool_id}")
async def get_tool(
    tool_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[SessionOrOperatorAuth, Depends(require_session_or_admin_operator)],
) -> dict[str, Any]:
    """Tool detail."""
    q = await db.execute(select(Tool).where(Tool.id == tool_id))
    row = q.scalar_one_or_none()
    if row is None:
        raise AgentFactoryException(
            "TOOL_NOT_FOUND", "Tool not found", status_code=404
        )
    return {
        "id": row.id,
        "version": row.version,
        "name": row.name,
        "description": row.description,
        "input_schema": row.input_schema,
        "output_schema": row.output_schema,
        "permission_required": row.permission_required,
        "timeout_seconds": row.timeout_seconds,
        "rate_limit": row.rate_limit,
        "implementation": row.implementation,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.put("/{tool_id}")
async def update_tool(
    tool_id: str,
    body: ToolUpdate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[RegistryAuth, Depends(require_tool_admin)],
) -> dict[str, Any]:
    """Update tool config."""
    q = await db.execute(select(Tool).where(Tool.id == tool_id))
    row = q.scalar_one_or_none()
    if row is None:
        raise AgentFactoryException(
            "TOOL_NOT_FOUND", "Tool not found", status_code=404
        )

    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.input_schema is not None:
        row.input_schema = body.input_schema
    if body.output_schema is not None:
        row.output_schema = body.output_schema
    if body.permission_required is not None:
        row.permission_required = body.permission_required
    if body.timeout_seconds is not None:
        row.timeout_seconds = body.timeout_seconds
    if body.rate_limit is not None:
        row.rate_limit = body.rate_limit
    if body.implementation is not None:
        row.implementation = body.implementation
    if body.status is not None:
        row.status = body.status

    return {"id": row.id, "status": "updated"}


class ToolApproveBody(BaseModel):
    note: str = Field("", max_length=512)


@router.post("/{tool_id}/approve")
async def approve_tool(
    tool_id: str,
    body: ToolApproveBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[RegistryAuth, Depends(require_tool_admin)],
) -> dict[str, Any]:
    """Second-sign activation when ``TOOL_DUAL_SIGN_ENABLED``."""
    s = get_settings()
    if not s.TOOL_DUAL_SIGN_ENABLED:
        raise AgentFactoryException(
            "FEATURE_DISABLED",
            "TOOL_DUAL_SIGN_ENABLED is false",
            status_code=400,
        )
    q = await db.execute(select(Tool).where(Tool.id == tool_id))
    row = q.scalar_one_or_none()
    if row is None:
        raise AgentFactoryException(
            "TOOL_NOT_FOUND", "Tool not found", status_code=404
        )
    if row.status != "pending_approval":
        raise AgentFactoryException(
            "INVALID_STATE",
            "Tool is not pending approval",
            status_code=409,
        )
    actor = _tool_operator_id(auth)
    if (
        auth != "bearer"
        and row.submitted_by_operator_id
        and row.submitted_by_operator_id == actor
    ):
        raise AgentFactoryException(
            "FORBIDDEN",
            "需要另一名管理员审批（不能与提交人相同）",
            status_code=403,
        )
    now = datetime.utcnow()
    row.status = "active"
    row.approved_by_operator_id = actor
    row.updated_at = now
    db.add(
        ToolApprovalLog(
            tool_id=row.id,
            actor_operator_id=actor,
            action="approve",
            detail={"note": body.note} if body.note else None,
            created_at=now,
        )
    )
    await db.flush()
    return {"id": row.id, "status": row.status}
