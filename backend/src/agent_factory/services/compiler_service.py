"""Skill Compiler service wrapper (DB + cache + pure compiler)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings
from agent_factory.core.compiler import compile_runspec
from agent_factory.core.multi_skill import (
    merge_secondary_skill_packages,
    parse_secondary_skill_refs,
)
from agent_factory.core.user_context import UserContext
from agent_factory.db.models.policy import OrgPolicy, PlatformPolicy
from agent_factory.db.models.run_spec import RunSpec
from agent_factory.db.models.skill import Skill
from agent_factory.db.models.tool import Tool
from agent_factory.services.agent_effective import resolve_compiler_agent_dict
from agent_factory.services.skill_discovery import (
    discover_skills_for_agent,
    expand_runspec_from_discovered_skills,
)
from agent_factory.services.skill_payload import skill_orm_to_compiler_pkg
from agent_factory.services.tool_gateway import ToolGateway

logger = logging.getLogger(__name__)


class CompilerService:
    """High-level compiler: DB -> dict RunSpec -> persist."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tool_gateway = ToolGateway()

    async def compile_and_save(
        self,
        *,
        db: AsyncSession,
        agent_id: str,
        user_ctx: UserContext,
        runtime_overrides: dict[str, Any] | None = None,
    ) -> RunSpec:
        """Load agent + skill + policies, compile, persist RunSpec."""
        # 1. Effective agent snapshot (release strategy / pinned / canary)
        agent_dict = await resolve_compiler_agent_dict(
            db,
            agent_id=agent_id,
            user_ctx=user_ctx,
        )

        # 2. Resolve skill
        skill_cfg = agent_dict.get("skill_config") or {}
        skill_id = skill_cfg.get("id")
        skill_version = skill_cfg.get("version_pin", "latest")
        if not skill_id:
            raise ValueError("Agent has no skill_config.id")

        q_skill = await db.execute(
            select(Skill)
            .where(Skill.id == skill_id)
            .order_by(Skill.version.desc())
        )
        skill_rows = q_skill.scalars().all()
        skill_row = None
        if skill_version == "latest":
            skill_row = skill_rows[0] if skill_rows else None
        else:
            for s in skill_rows:
                if s.version == skill_version:
                    skill_row = s
                    break
        if skill_row is None:
            raise ValueError(f"Skill not found: {skill_id}@{skill_version}")

        # 3. Load policies (latest enabled)
        platform_policy = await self._latest_platform_policy(db)
        org_policy = await self._latest_org_policy(db, user_ctx.department)

        # 4. Build serializable inputs for pure compiler
        skill_dict = skill_orm_to_compiler_pkg(skill_row)

        # 5. Gateway catalog: built-ins + active Tool Registry (http_api, etc.)
        available_tools = await self._gateway_available_tool_ids(db)

        if self.settings.MULTI_SKILL_ENABLED:
            refs = parse_secondary_skill_refs(agent_dict)
            secondary_pkgs: list[dict[str, Any]] = []
            for ref in refs:
                q_sec = await db.execute(
                    select(Skill).where(
                        Skill.id == ref["id"],
                        Skill.status == "active",
                    )
                )
                sec_rows = q_sec.scalars().all()
                sec_row = None
                ver = ref.get("version") or ""
                if ver:
                    for s in sec_rows:
                        if s.version == ver:
                            sec_row = s
                            break
                elif sec_rows:
                    sec_row = sec_rows[0]
                if sec_row is not None:
                    secondary_pkgs.append(skill_orm_to_compiler_pkg(sec_row))
            if secondary_pkgs:
                skill_dict, _ids = merge_secondary_skill_packages(
                    skill_dict,
                    secondary_pkgs,
                    agent_app=agent_dict,
                    user_ctx=user_ctx,
                    gateway_available=available_tools,
                    user_data_domains=(
                        list(user_ctx.data_domains)
                        if user_ctx.data_domains is not None
                        else None
                    ),
                )

        # 6. Compile
        runspec_dict = compile_runspec(
            agent_app=agent_dict,
            skill_pkg=skill_dict,
            platform_policy=platform_policy,
            org_policy=org_policy,
            user_ctx=user_ctx,
            available_tools=available_tools,
            user_data_domains=(
                list(user_ctx.data_domains)
                if user_ctx.data_domains is not None
                else None
            ),
            runtime_overrides=runtime_overrides,
        )

        # 6b. Dynamic skill discovery (Stage D)
        discovered = await discover_skills_for_agent(
            db,
            agent_skill_config=agent_dict.get("skill_config"),
            user_department=user_ctx.department,
        )
        if discovered:
            runspec_dict["allowed_tools"], runspec_dict["retrieval_scopes"] = (
                expand_runspec_from_discovered_skills(
                    runspec_dict.get("allowed_tools") or [],
                    runspec_dict.get("retrieval_scopes") or [],
                    discovered,
                )
            )

        # 7. Persist
        row = RunSpec(
            run_id=runspec_dict["run_id"],
            runspec_schema_version=runspec_dict["runspec_schema_version"],
            agent_id=runspec_dict["agent_id"],
            agent_version=runspec_dict["agent_version"],
            skill_id=runspec_dict["skill_id"],
            skill_version=runspec_dict["skill_version"],
            skill_package_hash=runspec_dict["skill_package_hash"],
            skill_file_manifest=runspec_dict.get("skill_file_manifest"),
            user_id_hash=runspec_dict["user_id_hash"],
            department=runspec_dict["department"],
            prompt_parts=runspec_dict["prompt_parts"],
            lazy_references=runspec_dict["lazy_references"],
            indexed_references=runspec_dict["indexed_references"],
            allowed_tools=runspec_dict["allowed_tools"],
            retrieval_scopes=runspec_dict["retrieval_scopes"],
            script_hooks=runspec_dict["script_hooks"],
            output_schema=runspec_dict["output_schema"],
            runtime=runspec_dict["runtime"],
            audit=runspec_dict["audit"],
            created_at=runspec_dict.get("created_at"),
            expires_at=None,
        )
        db.add(row)
        await db.flush()
        return row

    async def _gateway_available_tool_ids(self, db: AsyncSession) -> list[str]:
        """Ids the runner may execute: P0 built-ins plus ``tools.status=active``."""
        builtin = frozenset(self.tool_gateway._handlers.keys())
        q = await db.execute(select(Tool.id).where(Tool.status == "active"))
        reg = {str(tid) for tid in q.scalars().all()}
        return sorted(set(builtin) | reg)

    async def _merged_enabled_platform_prompts(self, db: AsyncSession) -> str | None:
        q = await db.execute(
            select(PlatformPolicy).order_by(
                PlatformPolicy.lineage_id,
                PlatformPolicy.version.desc(),
            )
        )
        rows = list(q.scalars().all())
        if not rows:
            return None
        by_lineage: dict[str, list[PlatformPolicy]] = {}
        for p in rows:
            by_lineage.setdefault(p.lineage_id, []).append(p)
        parts: list[str] = []
        for lid in sorted(by_lineage.keys()):
            vers = sorted(by_lineage[lid], key=lambda x: -x.version)
            chosen = next((x for x in vers if x.enabled), None)
            if chosen and chosen.prompt.strip():
                parts.append(chosen.prompt.strip())
        return "\n\n".join(parts) if parts else None

    async def _merged_enabled_org_prompt(
        self, db: AsyncSession, department: str | None
    ) -> str | None:
        if not department:
            return None
        q = await db.execute(
            select(OrgPolicy)
            .where(OrgPolicy.department == department)
            .order_by(OrgPolicy.lineage_id, OrgPolicy.version.desc())
        )
        rows = list(q.scalars().all())
        if not rows:
            return None
        by_lineage: dict[str, list[OrgPolicy]] = {}
        for p in rows:
            by_lineage.setdefault(p.lineage_id, []).append(p)
        parts: list[str] = []
        for lid in sorted(by_lineage.keys()):
            vers = sorted(by_lineage[lid], key=lambda x: -x.version)
            chosen = next((x for x in vers if x.enabled), None)
            if chosen and chosen.prompt.strip():
                parts.append(chosen.prompt.strip())
        return "\n\n".join(parts) if parts else None

    async def _latest_platform_policy(self, db: AsyncSession) -> str | None:
        return await self._merged_enabled_platform_prompts(db)

    async def _latest_org_policy(
        self, db: AsyncSession, department: str | None
    ) -> str | None:
        return await self._merged_enabled_org_prompt(db, department)
