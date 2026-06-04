"""POST /feedback — contract alias for docs/19-api-reference.md."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.api.deps import get_current_user
from agent_factory.api.v1.agents import FeedbackBody, _persist_feedback
from agent_factory.core.user_context import UserContext
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.infra.db import get_db_session
from agent_factory.middleware.error_handler import AgentFactoryException

router = APIRouter()


@router.post("/feedback")
async def post_feedback_root(
    body: FeedbackBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _user: Annotated[UserContext, Depends(get_current_user)],
) -> dict[str, str]:
    """Same as POST /agents/{agent_id}/feedback; session must exist."""
    q = await db.execute(
        select(ChatSession).where(ChatSession.session_id == body.session_id)
    )
    if q.scalar_one_or_none() is None:
        raise AgentFactoryException(
            "SESSION_NOT_FOUND",
            "Session not found",
            status_code=404,
        )
    return await _persist_feedback(db, body)
