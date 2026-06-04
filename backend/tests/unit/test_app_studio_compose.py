"""Integration-style tests for studio skill auto-creation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_factory.services.app_studio_service import (
    compose_and_register_agent,
    resolve_skill_for_requirements,
)


@pytest.mark.asyncio
async def test_resolve_creates_skill_when_no_match():
    db = AsyncMock()
    db.flush = AsyncMock()

    async def _execute(_stmt):
        q = MagicMock()
        q.scalar_one_or_none.return_value = None
        return q

    db.execute = AsyncMock(side_effect=_execute)

    with (
        patch(
            "agent_factory.services.app_studio_service.run_skill_registry_eval_gate",
            new=AsyncMock(),
        ),
        patch(
            "agent_factory.services.app_studio_service.publish_skill_changed",
            new=AsyncMock(),
        ),
    ):
        from agent_factory.services.app_studio_service import SkillCatalogEntry

        skill, created = await resolve_skill_for_requirements(
            db,
            requirements="帮我设计一个儿童绘本分镜与插画描述生成器",
            catalog=[
                SkillCatalogEntry(
                    id="problem-essence-analyst",
                    version="0.1.0",
                    name="问题本质分析",
                    description="组织根因",
                    when_to_use="部门推诿",
                )
            ],
            llm=None,
        )
    assert created is True
    assert skill.id.startswith("studio-")
    assert "儿童绘本" in skill.name or "儿童绘本" in skill.description


@pytest.mark.asyncio
async def test_resolve_creates_skill_when_llm_skill_id_missing():
    db = AsyncMock()
    db.flush = AsyncMock()

    async def _execute(_stmt):
        q = MagicMock()
        q.scalar_one_or_none.return_value = None
        return q

    db.execute = AsyncMock(side_effect=_execute)

    with (
        patch(
            "agent_factory.services.app_studio_service.run_skill_registry_eval_gate",
            new=AsyncMock(),
        ),
        patch(
            "agent_factory.services.app_studio_service.publish_skill_changed",
            new=AsyncMock(),
        ),
    ):
        from agent_factory.services.app_studio_service import SkillCatalogEntry

        skill, created = await resolve_skill_for_requirements(
            db,
            requirements="做一个全新的物联网设备运维助手",
            catalog=[
                SkillCatalogEntry(
                    id="demo-skill",
                    version="0.1.0",
                    name="Demo",
                    description="smoke",
                    when_to_use="test",
                )
            ],
            llm={
                "use_existing_skill": True,
                "skill_id": "nonexistent-skill-id",
                "name": "运维助手",
            },
            model_gateway=None,
        )
    assert created is True
    assert skill.id.startswith("studio-")
