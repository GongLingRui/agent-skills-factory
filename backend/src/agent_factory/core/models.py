"""Pydantic domain models (shared schemas)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentAppOut(BaseModel):
    id: str
    name: str
    description: str = ""
    version: str
    lifecycle_state: str
    tags: list[str] = []
    ui_config: dict[str, Any] = {}


class SkillOut(BaseModel):
    id: str
    version: str
    name: str | None
    description: str | None
    risk_tier: str | None
    status: str
    created_at: datetime | None


class ToolOut(BaseModel):
    id: str
    version: str | None
    name: str | None
    description: str | None
    status: str
    created_at: datetime | None


class RunSpecOut(BaseModel):
    run_id: str
    agent_id: str | None
    agent_version: str | None
    skill_id: str | None
    skill_version: str | None
    user_id_hash: str
    department: str | None
    allowed_tools: list[str] = []
    retrieval_scopes: list[str] = []
    output_schema: str | None
    runtime: dict[str, Any] = {}
    audit: dict[str, Any] = {}
    created_at: datetime | None


class ChatMessage(BaseModel):
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None


class SSEEvent(BaseModel):
    type: str
    delta: str | None = None
    output: str | None = None
    tool_id: str | None = None
    call_id: str | None = None
    status: str | None = None
    preview: str | None = None
    schema_valid: bool | None = None
    message_id: str | None = None
    code: str | None = None
    message: str | None = None


class FeedbackIn(BaseModel):
    session_id: str = Field(..., min_length=1)
    message_id: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    feedback: str = Field(..., pattern="^(thumbs_up|thumbs_down)$")
    reasons: list[str] = []
    comment: str = Field("", max_length=200)
