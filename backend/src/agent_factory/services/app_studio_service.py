"""Compose Agent App from natural-language requirements + Skill catalog."""

from __future__ import annotations

import json
import logging
import re
import secrets
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.core.tool_catalog import STUDIO_DEFAULT_TOOL_IDS, catalog_for_api
from agent_factory.core.tool_planner import plan_tools_for_requirements
from agent_factory.core.rbac import RegistryDeptScope
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.db.models.skill import Skill
from agent_factory.infra.skill_notify import publish_skill_changed
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.agent_registry_service import register_agent
from agent_factory.services.agent_yaml import validate_agent_id
from agent_factory.services.model_gateway import ModelGateway
from agent_factory.services.repo_skill_bundle import (
    build_package_metadata_for_skill_dir,
    compute_skill_package_hash,
)
from agent_factory.services.skill_eval_gate import run_skill_registry_eval_gate

logger = logging.getLogger(__name__)

_DEFAULT_TOOLS = list(STUDIO_DEFAULT_TOOL_IDS)
_SKILL_VERSION = "0.1.0"
# 低于该分数视为与现有 Skill 无有效匹配，将自动创建新 Skill
_SKILL_MATCH_MIN_SCORE = 2.5
# 多个候选接近时，最佳须明显领先次优，避免泛化关键词误绑
_SKILL_MATCH_MIN_MARGIN = 2.0


@dataclass(frozen=True)
class SkillCatalogEntry:
    id: str
    version: str
    name: str
    description: str
    when_to_use: str


@dataclass(frozen=True)
class SkillMatchResult:
    skill: SkillCatalogEntry | None
    score: float
    runner_up_score: float = 0.0


async def _load_skill_catalog(db: AsyncSession) -> list[SkillCatalogEntry]:
    """Latest active version per skill id."""
    q = await db.execute(
        select(Skill).where(Skill.status == "active").order_by(Skill.id, Skill.version)
    )
    rows = list(q.scalars().all())
    by_id: dict[str, Skill] = {}
    for row in rows:
        by_id[row.id] = row
    out: list[SkillCatalogEntry] = []
    for sid in sorted(by_id.keys()):
        s = by_id[sid]
        out.append(
            SkillCatalogEntry(
                id=s.id,
                version=s.version,
                name=(s.name or s.id).strip(),
                description=(s.description or "").strip(),
                when_to_use=(s.when_to_use or "").strip(),
            )
        )
    return out


def _tokenize(text: str) -> set[str]:
    return {
        t.lower()
        for t in re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower())
    }


def _score_skill(requirements: str, skill: SkillCatalogEntry) -> float:
    msg = requirements.lower()
    tokens = _tokenize(requirements)
    score = 0.0
    hay = " ".join(
        filter(
            None,
            [skill.name, skill.description, skill.when_to_use, skill.id],
        )
    ).lower()
    for tok in tokens:
        if tok in hay:
            score += 1.0
    if skill.name.lower() in msg:
        score += 3.0
    if skill.id.replace("-", " ") in msg:
        score += 2.0
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,8}", skill.when_to_use):
        if phrase in requirements:
            score += 2.5
    return score


def find_best_skill_match(
    requirements: str,
    catalog: list[SkillCatalogEntry],
) -> SkillMatchResult:
    """Return best catalog skill and score; ``skill`` is None when catalog empty."""
    if not catalog:
        return SkillMatchResult(skill=None, score=0.0)
    scored = sorted(
        ((_score_skill(requirements, s), s) for s in catalog),
        key=lambda x: x[0],
        reverse=True,
    )
    best_score, best = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    return SkillMatchResult(
        skill=best,
        score=best_score,
        runner_up_score=runner_up,
    )


def skill_match_is_confident(match: SkillMatchResult) -> bool:
    if match.skill is None or match.score < _SKILL_MATCH_MIN_SCORE:
        return False
    if match.runner_up_score <= 0.0:
        return True
    margin = match.score - match.runner_up_score
    return margin >= _SKILL_MATCH_MIN_MARGIN


def _derive_display_name(requirements: str) -> str:
    line = requirements.strip().splitlines()[0].strip()
    if len(line) > 48:
        line = line[:45] + "…"
    return line or "自定义应用"


def _slug_skill_id(requirements: str, hint: str | None = None) -> str:
    raw = (hint or "").strip().lower()
    if not raw:
        raw = f"studio-{secrets.token_hex(4)}"
    base = re.sub(r"[^a-z0-9-]", "-", raw)
    base = re.sub(r"-+", "-", base).strip("-")
    if not base or not re.match(r"^[a-z0-9]", base):
        base = f"studio-{secrets.token_hex(4)}"
    if len(base) > 56:
        base = base[:56].rstrip("-")
    return base


async def _ensure_unique_skill_id(
    db: AsyncSession,
    requirements: str,
    hint: str | None = None,
) -> str:
    for _ in range(10):
        sid = _slug_skill_id(requirements, hint)
        q = await db.execute(
            select(Skill.id).where(Skill.id == sid, Skill.version == _SKILL_VERSION)
        )
        if q.scalar_one_or_none() is None:
            validate_agent_id(sid)
            return sid
        hint = None
    raise AgentFactoryException(
        "INTERNAL_ERROR",
        "无法生成唯一 Skill ID，请重试",
        status_code=500,
    )


def _default_skill_body(
    *,
    name: str,
    description: str,
    when_to_use: str,
    requirements: str,
) -> str:
    return (
        f"# {name}\n\n"
        f"## 概述\n{description}\n\n"
        f"## 适用场景\n{when_to_use}\n\n"
        "## 工作方式\n"
        "1. 先理解用户的具体场景与目标，必要时追问关键信息。\n"
        "2. 按领域最佳实践组织分析与建议，避免空泛套话。\n"
        "3. 输出结构清晰、可执行，并标注需人工复核的部分。\n\n"
        "## 输出要求\n"
        "- 使用简体中文，分点或分段呈现。\n"
        "- 先结论后依据；不确定时明确说明。\n"
        "- 不编造事实或引用来源。\n\n"
        "## 创建时的用户需求（上下文）\n"
        f"{requirements.strip()}\n"
    )


def _extract_new_skill_spec(
    requirements: str,
    llm: dict[str, Any] | None,
) -> dict[str, str]:
    llm = llm or {}
    nested = llm.get("new_skill")
    nested_dict = nested if isinstance(nested, dict) else {}

    def _pick(*keys: str, default: str = "") -> str:
        for key in keys:
            for src in (nested_dict, llm):
                val = src.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return default

    name = _pick("name", default=_derive_display_name(requirements))[:128]
    description = _pick("description", default=requirements[:500])[:2000]
    when_to_use = _pick("when_to_use", default=requirements[:400])[:2000]
    skill_body = _pick(
        "skill_body",
        default=_default_skill_body(
            name=name,
            description=description,
            when_to_use=when_to_use,
            requirements=requirements,
        ),
    )
    id_hint = _pick("id", "skill_id", default="")
    return {
        "name": name,
        "description": description,
        "when_to_use": when_to_use,
        "skill_body": skill_body,
        "id_hint": id_hint,
    }


async def create_studio_skill(
    db: AsyncSession,
    *,
    requirements: str,
    llm: dict[str, Any] | None = None,
    model_gateway: ModelGateway | None = None,
    settings: Settings | None = None,
) -> SkillCatalogEntry:
    """Register a new Skill when no catalog entry matches user requirements."""
    cfg = settings or get_settings()
    llm_payload = llm
    if model_gateway is not None and not _llm_has_rich_new_skill(llm_payload):
        llm_payload = await _ensure_new_skill_llm_spec(
            model_gateway,
            cfg,
            requirements=requirements,
            llm=llm_payload,
        )
    spec = _extract_new_skill_spec(requirements, llm_payload)
    skill_id = await _ensure_unique_skill_id(
        db,
        requirements,
        spec["id_hint"] or None,
    )
    tools_meta: dict[str, list[str]] = {
        "require": [],
        "optional": list(_DEFAULT_TOOLS),
    }
    tools_raw = (llm_payload or {}).get("tools")
    if isinstance(tools_raw, dict):
        raw_allow = tools_raw.get("allow")
        if isinstance(raw_allow, list):
            merged = [str(x).strip() for x in raw_allow if str(x).strip()]
            if merged:
                tools_meta = {"require": [], "optional": merged}
    pkg_meta = build_package_metadata_for_skill_dir(
        skill_id=skill_id,
        skill_body=spec["skill_body"],
        reference_files={},
        lazy_refs=[],
        file_manifest={},
        tools=tools_meta,
    )
    settings = get_settings()
    await run_skill_registry_eval_gate(
        package_metadata=pkg_meta,
        settings=settings,
    )
    pkg_hash = compute_skill_package_hash(
        skill_id=skill_id,
        skill_version=_SKILL_VERSION,
        skill_body=spec["skill_body"],
        file_manifest={},
    )
    row = Skill(
        id=skill_id,
        version=_SKILL_VERSION,
        name=spec["name"],
        description=spec["description"],
        when_to_use=spec["when_to_use"],
        owner="studio",
        risk_tier="low",
        skill_package_hash=pkg_hash,
        package_metadata=pkg_meta,
        storage_path=f"skills/studio/{skill_id}",
        status="active",
    )
    db.add(row)
    await db.flush()
    await publish_skill_changed(
        skill_id=row.id,
        version=row.version,
        action="created",
    )
    logger.info(
        "app_studio_skill_created",
        extra={"skill_id": skill_id, "requirements_len": len(requirements)},
    )
    return SkillCatalogEntry(
        id=row.id,
        version=row.version,
        name=spec["name"],
        description=spec["description"],
        when_to_use=spec["when_to_use"],
    )


def _slug_agent_id(skill_id: str) -> str:
    suffix = secrets.token_hex(3)
    base = re.sub(r"[^a-z0-9-]", "-", skill_id.lower())
    base = re.sub(r"-+", "-", base).strip("-")[:40] or "skill"
    candidate = f"{base}-app-{suffix}"
    if len(candidate) > 64:
        candidate = f"app-{suffix}-{base[:48]}"
    return candidate[:64]


async def _ensure_unique_agent_id(db: AsyncSession, skill_id: str) -> str:
    for _ in range(8):
        aid = _slug_agent_id(skill_id)
        q = await db.execute(select(AgentApp.id).where(AgentApp.id == aid))
        if q.scalar_one_or_none() is None:
            return aid
    raise AgentFactoryException(
        "INTERNAL_ERROR",
        "无法生成唯一 Agent ID，请重试",
        status_code=500,
    )


def _build_agent_body(
    *,
    requirements: str,
    skill: SkillCatalogEntry,
    agent_id: str,
    llm: dict[str, Any] | None,
    tools_allow: list[str] | None = None,
) -> dict[str, Any]:
    llm = llm or {}
    name = str(llm.get("name") or skill.name or skill.id).strip()[:128]
    description = str(
        llm.get("description") or skill.description or requirements[:240]
    ).strip()
    instruction = str(
        llm.get("instruction")
        or (
            f"你是{name}，基于 Skill「{skill.name}」为用户提供服务。\n"
            f"创建该应用时的用户需求：{requirements.strip()}\n"
            "请严格遵循绑定 Skill 的工作流、工具与输出契约。"
        )
    ).strip()
    ui_raw = llm.get("ui_config")
    ui: dict[str, str] = {}
    if isinstance(ui_raw, dict):
        for key in ("title", "welcome_message", "input_placeholder"):
            val = ui_raw.get(key)
            if isinstance(val, str) and val.strip():
                ui[key] = val.strip()
    ui.setdefault("title", name)
    ui.setdefault(
        "welcome_message",
        f"你好！我是{name}。请描述你的具体场景或问题，我会按专业能力协助你。",
    )
    ui.setdefault("input_placeholder", "描述你的需求…")
    tags_raw = llm.get("tags")
    tags: list[str] = ["工作室"]
    if isinstance(tags_raw, list):
        for t in tags_raw:
            s = str(t).strip()
            if s and s not in tags:
                tags.append(s)
    tools_allow_final = list(tools_allow) if tools_allow else None
    if tools_allow_final is None:
        llm_tools = llm.get("tools")
        if isinstance(llm_tools, dict):
            raw_allow = llm_tools.get("allow")
            if isinstance(raw_allow, list) and raw_allow:
                tools_allow_final = [str(t).strip() for t in raw_allow if str(t).strip()]
    if not tools_allow_final:
        tools_allow_final = list(_DEFAULT_TOOLS)
    return {
        "id": agent_id,
        "name": name,
        "version": "0.1.0",
        "description": description,
        "instruction": instruction,
        "runspec_schema_version": 1,
        "owner": "studio",
        "lifecycle_state": "active",
        "tags": tags,
        "model_policy": {"default": "MiniMax-M2.7", "fallback": "MiniMax-M2.7"},
        "skill": {"id": skill.id, "version_pin": skill.version},
        "tools": {"allow": tools_allow_final},
        "knowledge_scopes": [],
        "limits": {
            "max_turns": 10,
            "max_tokens": 8000,
            "timeout_seconds": 120,
        },
        "release": {"strategy": "full"},
        "enterprise": {"risk_tier": "low"},
        "ui_config": ui,
    }


async def _collect_chat_text(
    gateway: ModelGateway,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
) -> str:
    parts: list[str] = []
    async for chunk in gateway.chat(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.2,
        tools=None,
        concurrency_class="batch",
        queue_priority=3,
    ):
        for choice in chunk.choices:
            if choice.delta:
                parts.append(choice.delta)
    return "".join(parts).strip()


async def _compose_with_llm(
    gateway: ModelGateway,
    settings: Settings,
    *,
    requirements: str,
    catalog: list[SkillCatalogEntry],
) -> dict[str, Any] | None:
    model = (settings.ROUTER_MODEL or "").strip() or "MiniMax-M2.7"
    skills_json = [
        {
            "skill_id": s.id,
            "version": s.version,
            "name": s.name,
            "description": s.description[:300],
            "when_to_use": s.when_to_use[:300],
        }
        for s in catalog
    ]
    system = (
        "你是企业 Agent 应用编排助手。根据用户需求：\n"
        "默认假设现有 Skill 目录中没有完全合适的条目，应创建新 Skill（use_existing_skill=false）。\n"
        "仅当某现有 Skill 与需求在领域、任务、输出形态上高度一致时，"
        "才设 use_existing_skill=true 并填写 skill_id。\n"
        "创建新 Skill 时，new_skill.skill_body 须为完整 Markdown："
        "含概述、适用场景、分步工作流、输出格式/约束，贴合用户需求，"
        "不要空泛模板。\n"
        "tools.allow 从 OpenClaw 风格目录选择，可用 preset：minimal/coding/web/browser/agents/full，"
        "或 tools.allow 数组（如 fs.read、web.search、mcp.context7.query_docs、agent.spawn）。\n"
        "只输出 JSON："
        '{"use_existing_skill":true,"skill_id":"...",'
        '"name":"应用名","description":"...","instruction":"...",'
        '"tools":{"allow":["kb.search","doc.extract","read_reference"]},'
        '"ui_config":{"title":"...","welcome_message":"...","input_placeholder":"..."},'
        '"tags":["..."]}'
        " 或 "
        '{"use_existing_skill":false,"new_skill":{"id":"my-skill-id","name":"...",'
        '"description":"...","when_to_use":"...","skill_body":"markdown..."},'
        '"name":"应用名","instruction":"...","tools":{"allow":[...]},'
        '"ui_config":{...},"tags":[...]}'
    )
    user = (
        f"Skill 目录：\n{json.dumps(skills_json, ensure_ascii=False)}\n\n"
        f"用户需求：\n{requirements.strip()}"
    )
    try:
        text = await _collect_chat_text(
            gateway,
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=min(4096, max(2000, settings.ROUTER_LLM_MAX_TOKENS * 12)),
        )
    except Exception:
        logger.exception("app_studio_llm_failed")
        return None
    obj = extract_json_object_from_text(text)
    if not obj and text:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


def _llm_has_rich_new_skill(llm: dict[str, Any] | None) -> bool:
    if not llm:
        return False
    nested = llm.get("new_skill")
    if not isinstance(nested, dict):
        return False
    body = nested.get("skill_body")
    return isinstance(body, str) and len(body.strip()) >= 120


async def _generate_new_skill_with_llm(
    gateway: ModelGateway,
    settings: Settings,
    *,
    requirements: str,
) -> dict[str, str] | None:
    """Dedicated LLM call to author a new Skill when compose output lacks skill_body."""
    model = (settings.ROUTER_MODEL or "").strip() or "MiniMax-M2.7"
    system = (
        "你是 Skill 包作者。根据用户需求输出一个 JSON 对象，字段："
        'id（kebab-case 英文）、name、description、when_to_use、skill_body（Markdown，'
        "含概述、适用场景、工作流步骤、输出要求，贴合需求）。"
        "tools 固定为 kb.search/doc.extract/read_reference 的可选子集，"
        "在 skill_body 中说明何时调用检索或读附件。"
        "只输出 JSON，不要 markdown 围栏。"
    )
    try:
        text = await _collect_chat_text(
            gateway,
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": requirements.strip()},
            ],
            max_tokens=min(4096, max(2000, settings.ROUTER_LLM_MAX_TOKENS * 12)),
        )
    except Exception:
        logger.exception("app_studio_skill_llm_failed")
        return None
    obj = extract_json_object_from_text(text)
    if not isinstance(obj, dict):
        return None
    out: dict[str, str] = {}
    for key in ("id", "name", "description", "when_to_use", "skill_body"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    if not out.get("skill_body"):
        return None
    return out


async def _ensure_new_skill_llm_spec(
    gateway: ModelGateway,
    settings: Settings,
    *,
    requirements: str,
    llm: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(llm or {})
    generated = await _generate_new_skill_with_llm(
        gateway,
        settings,
        requirements=requirements,
    )
    if not generated:
        return merged
    nested = merged.get("new_skill")
    nested_dict = dict(nested) if isinstance(nested, dict) else {}
    nested_dict.update({k: v for k, v in generated.items() if v})
    merged["new_skill"] = nested_dict
    merged.setdefault("use_existing_skill", False)
    for key in ("name", "description"):
        if key not in merged and generated.get(key):
            merged[key] = generated[key]
    return merged


def _sanitize_llm_for_new_skill(llm: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop stale skill_id hints when falling back to auto-create."""
    if not llm:
        return llm
    cleaned = dict(llm)
    cleaned.pop("skill_id", None)
    cleaned["use_existing_skill"] = False
    nested = cleaned.get("new_skill")
    if isinstance(nested, dict):
        nested_copy = dict(nested)
        nested_copy.pop("id", None)
        cleaned["new_skill"] = nested_copy
    return cleaned


def _llm_wants_new_skill(llm: dict[str, Any] | None) -> bool:
    if not llm:
        return False
    if llm.get("use_existing_skill") is False:
        return True
    if llm.get("create_new_skill") is True:
        return True
    sid = str(llm.get("skill_id") or "").strip()
    return not sid and isinstance(llm.get("new_skill"), dict)


def _llm_existing_skill_id(
    llm: dict[str, Any] | None,
    catalog: list[SkillCatalogEntry],
) -> SkillCatalogEntry | None:
    if not llm or _llm_wants_new_skill(llm):
        return None
    sid = str(llm.get("skill_id") or "").strip()
    if not sid:
        return None
    return next((s for s in catalog if s.id == sid), None)


async def resolve_skill_for_requirements(
    db: AsyncSession,
    *,
    requirements: str,
    catalog: list[SkillCatalogEntry],
    llm: dict[str, Any] | None,
    model_gateway: ModelGateway | None = None,
    settings: Settings | None = None,
) -> tuple[SkillCatalogEntry, bool]:
    """Return (skill, skill_was_created)."""
    cfg = settings or get_settings()
    llm_existing = _llm_existing_skill_id(llm, catalog)
    if llm_existing is not None:
        return llm_existing, False

    if _llm_wants_new_skill(llm):
        created = await create_studio_skill(
            db,
            requirements=requirements,
            llm=llm,
            model_gateway=model_gateway,
            settings=cfg,
        )
        return created, True

    # LLM 指定了不存在的 skill_id → 自动创建，避免误落 keyword 匹配
    if llm and llm.get("use_existing_skill") is True:
        sid = str(llm.get("skill_id") or "").strip()
        if sid and not any(s.id == sid for s in catalog):
            logger.warning(
                "app_studio_llm_skill_not_found",
                extra={"skill_id": sid},
            )
            created = await create_studio_skill(
                db,
                requirements=requirements,
                llm=_sanitize_llm_for_new_skill(llm),
                model_gateway=model_gateway,
                settings=cfg,
            )
            return created, True

    match = find_best_skill_match(requirements, catalog)
    if skill_match_is_confident(match):
        assert match.skill is not None
        return match.skill, False

    created = await create_studio_skill(
        db,
        requirements=requirements,
        llm=llm,
        model_gateway=model_gateway,
        settings=cfg,
    )
    return created, True


async def compose_and_register_agent(
    db: AsyncSession,
    *,
    requirements: str,
    model_gateway: ModelGateway | None,
    created_by: str,
    dept_scope: RegistryDeptScope | None,
    tool_preset: str | None = None,
    tools_allow: list[str] | None = None,
) -> dict[str, Any]:
    """Match or create Skill, build agent.yaml-shaped body, register AgentApp."""
    req = requirements.strip()
    if len(req) < 4:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "请至少用几句话描述你想创建的应用需求",
            status_code=400,
        )
    if len(req) > 4000:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "需求描述过长（最多 4000 字符）",
            status_code=400,
        )

    catalog = await _load_skill_catalog(db)
    settings = get_settings()
    llm_out: dict[str, Any] | None = None
    if model_gateway is not None:
        llm_out = await _compose_with_llm(
            model_gateway,
            settings,
            requirements=req,
            catalog=catalog,
        )

    skill, skill_created = await resolve_skill_for_requirements(
        db,
        requirements=req,
        catalog=catalog,
        llm=llm_out,
        model_gateway=model_gateway,
        settings=settings,
    )

    agent_id = await _ensure_unique_agent_id(db, skill.id)
    planned_tools = plan_tools_for_requirements(
        req,
        preset=tool_preset,
        selected=tools_allow,
        llm_allow=(
            (llm_out.get("tools") or {}).get("allow")
            if isinstance(llm_out, dict) and isinstance(llm_out.get("tools"), dict)
            else None
        ),
        settings=settings,
    )
    body = _build_agent_body(
        requirements=req,
        skill=skill,
        agent_id=agent_id,
        llm=llm_out,
        tools_allow=planned_tools,
    )
    agent = await register_agent(
        db,
        body,
        created_by=created_by,
        dept_scope=dept_scope,
    )
    if skill_created:
        planner = "new_skill"
    elif llm_out and _llm_existing_skill_id(llm_out, catalog):
        planner = "llm"
    elif llm_out:
        planner = "llm"
    else:
        planner = "keyword"
    return {
        "id": agent.id,
        "name": agent.name,
        "version": agent.version,
        "skill_id": skill.id,
        "skill_version": skill.version,
        "skill_created": skill_created,
        "status": "created",
        "planner": planner,
        "tools_allow": planned_tools,
    }
