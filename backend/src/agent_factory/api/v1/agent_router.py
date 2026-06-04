"""Router Agent API (prd P3)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.api.deps import get_current_user
from agent_factory.core.user_context import UserContext
from agent_factory.infra.db import get_db_session
from agent_factory.services.factory import get_model_gateway
from agent_factory.services.router_service import route_to_agent

router = APIRouter()


class RouterRouteRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    candidate_agent_ids: list[str] = Field(..., min_length=1, max_length=32)


@router.post("/route")
async def post_route_agent(
    body: RouterRouteRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[UserContext, Depends(get_current_user)],
) -> dict[str, Any]:
    """Select best Agent App for a unified entry (keyword router v1)."""
    gateway = get_model_gateway()
    return await route_to_agent(
        db,
        user_message=body.message,
        candidate_agent_ids=body.candidate_agent_ids,
        department=user.department,
        model_gateway=gateway,
    )
