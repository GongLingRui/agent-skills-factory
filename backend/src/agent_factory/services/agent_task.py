"""Lightweight agent task system (Stage C).

P0: in-memory registry backed by asyncio Tasks. Production may replace with
Redis Streams + Celery / RQ workers.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentTask:
    """Agent background task state."""

    task_id: str
    agent_id: str
    session_id: str
    status: str  # pending, running, done, error
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(
        default_factory=lambda: asyncio.get_event_loop().time()
    )
    updated_at: float = field(
        default_factory=lambda: asyncio.get_event_loop().time()
    )


class TaskManager:
    """In-memory task registry (P0)."""

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTask] = {}

    def create(self, agent_id: str, session_id: str) -> AgentTask:
        task = AgentTask(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            session_id=session_id,
            status="pending",
        )
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> AgentTask | None:
        return self._tasks.get(task_id)

    def set_running(self, task_id: str) -> None:
        t = self._tasks.get(task_id)
        if t:
            t.status = "running"
            t.updated_at = asyncio.get_event_loop().time()

    def set_done(self, task_id: str, result: dict[str, Any]) -> None:
        t = self._tasks.get(task_id)
        if t:
            t.status = "done"
            t.result = result
            t.updated_at = asyncio.get_event_loop().time()

    def set_error(self, task_id: str, error: str) -> None:
        t = self._tasks.get(task_id)
        if t:
            t.status = "error"
            t.error = error
            t.updated_at = asyncio.get_event_loop().time()


# Global singleton (P0)
_task_manager = TaskManager()


def get_task_manager() -> TaskManager:
    return _task_manager
