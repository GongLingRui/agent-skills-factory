"""System initialization script: seed roles, permissions, policies, tools, config.

Usage:
    source .venv/bin/activate
    python scripts/init_db.py

Requires DATABASE_URL env (or .env file).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path so imports work when running as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from agent_factory.config import get_settings
from agent_factory.db.models import (
    Permission,
    PlatformPolicy,
    Role,
    RolePermission,
    SystemConfig,
    Tool,
)

logger = logging.getLogger("init_db")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Seed data aligned with docs/23-system-init.md

ROLES = [
    (
        "platform_admin",
        "平台管理员",
        (
            "全平台管理：Agent/Skill/Tool 增删改、"
            "降级开关、审计查看"
        ),
    ),
    (
        "department_admin",
        "部门管理员",
        (
            "本部门管理：Agent 配置修改、"
            "灰度发布、用户权限分配"
        ),
    ),
    ("agent_owner", "Agent 所有者", "单个 Agent 管理：修改 ui_config / prompt"),
    ("user", "普通用户", "仅使用权限：查看有权限的 Agent、发起对话"),
]

PERMISSIONS = [
    ("agent.read", "查看 Agent", "agent", "read"),
    ("agent.write", "创建修改 Agent", "agent", "write"),
    ("agent.admin", "下架灰度管理", "agent", "admin"),
    ("skill.publish", "注册升级 Skill", "skill", "publish"),
    ("skill.read", "查看 Skill", "skill", "read"),
    ("tool.admin", "注册禁用 Tool", "tool", "admin"),
    ("audit.read", "查看审计日志", "audit", "read"),
    ("degradation.control", "手动触发降级", "degradation", "control"),
]

ROLE_PERMISSIONS = [
    # platform_admin
    ("platform_admin", "agent.read"),
    ("platform_admin", "agent.write"),
    ("platform_admin", "agent.admin"),
    ("platform_admin", "skill.publish"),
    ("platform_admin", "skill.read"),
    ("platform_admin", "tool.admin"),
    ("platform_admin", "audit.read"),
    ("platform_admin", "degradation.control"),
    # department_admin
    ("department_admin", "agent.read"),
    ("department_admin", "agent.write"),
    ("department_admin", "agent.admin"),
    ("department_admin", "skill.read"),
    # agent_owner
    ("agent_owner", "agent.read"),
    ("agent_owner", "agent.write"),
    # user
    ("user", "agent.read"),
]

PLATFORM_POLICY = {
    "lineage_id": "default",
    "version": 1,
    "prompt": (
        "你是央企内部智能助手。你的回答必须：\n"
        "1. 不涉及国家秘密、商业秘密\n"
        "2. 不给出法律意见替代专业律师\n"
        "3. 不泄露其他用户信息\n"
        "4. 不确定时明确标注\"需人工复核\"\n"
        "5. 引用公司制度时必须标注文号和生效日期"
    ),
    "enabled": True,
}

TOOLS = [
    {
        "id": "kb.search",
        "version": "1.0.0",
        "name": "知识库检索",
        "description": "在内部知识库中检索与 query 相关的文档片段",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "scope": {"type": "string"},
                "top_k": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "doc_id": {"type": "string"},
                            "content": {"type": "string"},
                            "score": {"type": "number"},
                        },
                    },
                },
            },
        },
        "permission_required": ["knowledge.read"],
        "timeout_seconds": 10,
        "rate_limit": {"per_user": 60, "per_agent": 500, "global": 1000},
        "implementation": {"type": "http_api", "endpoint": "https://kb.internal/search"},
        "status": "active",
    },
    {
        "id": "doc.extract",
        "version": "1.0.0",
        "name": "文档解析",
        "description": (
            "解析上传的文档（PDF/DOCX/TXT），提取正文内容；"
            "支持按页码或分块按需拉取"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "format": {
                    "type": "string",
                    "enum": ["text", "markdown", "structured"],
                    "default": "text",
                },
                "page_start": {"type": "integer"},
                "page_end": {"type": "integer"},
                "chunk_index": {"type": "integer"},
            },
            "required": ["file_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "pages": {"type": "integer"},
                "chunks_total": {"type": "integer"},
                "current_chunk": {"type": "integer"},
                "sections": {"type": "array"},
            },
        },
        "permission_required": ["document.read"],
        "timeout_seconds": 60,
        "rate_limit": {"per_user": 20, "per_agent": 100, "global": 500},
        "implementation": {
            "type": "http_api",
            "endpoint": "http://doc-worker.internal:8080/extract",
        },
        "status": "active",
    },
    {
        "id": "read_reference",
        "version": "1.0.0",
        "name": "读取 Skill 引用",
        "description": "按名称读取 Skill Package 中 on_demand 的 reference 文件",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "source": {"type": "string"},
            },
        },
        "permission_required": [],
        "timeout_seconds": 5,
        "rate_limit": {"per_user": 120, "per_agent": 1000, "global": 5000},
        "implementation": {
            "type": "internal_function",
            "endpoint": "skill_registry.read_reference",
        },
        "status": "active",
    },
    {
        "id": "risk.rule_check",
        "version": "1.0.0",
        "name": "规则风险扫描（占位）",
        "description": (
            "对条款/正文做规则命中与风险分级（P0 占位实现；"
            "生产环境接入法务规则引擎或内部 HTTP Tool）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "clause": {"type": "string"},
            },
            "description": "Provide text or clause (prd §5 examples).",
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "risk_level": {"type": "string"},
                "summary": {"type": "string"},
                "rule_hits": {"type": "array"},
                "requires_human_review": {"type": "boolean"},
            },
        },
        "permission_required": [],
        "timeout_seconds": 15,
        "rate_limit": {"per_user": 30, "per_agent": 200, "global": 1000},
        "implementation": {
            "type": "internal_function",
            "endpoint": "tool_gateway.risk.rule_check",
        },
        "status": "active",
    },
]

WORKSPACE_TOOLS = [
    {
        "id": "fs.read",
        "version": "1.0.0",
        "name": "读取文件",
        "description": (
            "读取工作区内的文本文件；支持 offset/limit 分页（对标 Claude Code Read）"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "工作区内文件路径"},
                "offset": {"type": "integer", "description": "起始行号（1-based）"},
                "limit": {"type": "integer", "description": "最多读取行数"},
            },
            "required": ["file_path"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "total_lines": {"type": "integer"},
            },
        },
        "permission_required": [],
        "timeout_seconds": 15,
        "rate_limit": {"per_user": 120, "per_agent": 2000, "global": 10000},
        "implementation": {"type": "internal_function", "endpoint": "workspace.fs.read"},
        "status": "active",
    },
    {
        "id": "fs.write",
        "version": "1.0.0",
        "name": "写入文件",
        "description": "创建或覆盖工作区文件（对标 Write）",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file_path", "content"],
        },
        "output_schema": {"type": "object"},
        "permission_required": ["agent.write"],
        "timeout_seconds": 15,
        "rate_limit": {"per_user": 60, "per_agent": 500, "global": 5000},
        "implementation": {"type": "internal_function", "endpoint": "workspace.fs.write"},
        "status": "active",
    },
    {
        "id": "fs.edit",
        "version": "1.0.0",
        "name": "编辑文件",
        "description": "按 old_string/new_string 定点替换（对标 Edit）",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
        "output_schema": {"type": "object"},
        "permission_required": ["agent.write"],
        "timeout_seconds": 15,
        "rate_limit": {"per_user": 60, "per_agent": 500, "global": 5000},
        "implementation": {"type": "internal_function", "endpoint": "workspace.fs.edit"},
        "status": "active",
    },
    {
        "id": "fs.glob",
        "version": "1.0.0",
        "name": "Glob 文件",
        "description": "按 glob 模式列出工作区文件路径（对标 Glob）",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "搜索根目录，默认工作区根"},
            },
            "required": ["pattern"],
        },
        "output_schema": {"type": "object"},
        "permission_required": [],
        "timeout_seconds": 20,
        "rate_limit": {"per_user": 60, "per_agent": 500, "global": 5000},
        "implementation": {"type": "internal_function", "endpoint": "workspace.fs.glob"},
        "status": "active",
    },
    {
        "id": "fs.grep",
        "version": "1.0.0",
        "name": "Grep 搜索",
        "description": "在工作区内容中搜索（优先 ripgrep，对标 Grep）",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "glob": {"type": "string"},
                "head_limit": {"type": "integer"},
                "ignore_case": {"type": "boolean"},
            },
            "required": ["pattern"],
        },
        "output_schema": {"type": "object"},
        "permission_required": [],
        "timeout_seconds": 30,
        "rate_limit": {"per_user": 60, "per_agent": 500, "global": 5000},
        "implementation": {"type": "internal_function", "endpoint": "workspace.fs.grep"},
        "status": "active",
    },
    {
        "id": "shell.exec",
        "version": "1.0.0",
        "name": "Shell 命令",
        "description": "在工作区目录执行 shell 命令（对标 Bash；需 SHELL_EXEC_ENABLED）",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["command"],
        },
        "output_schema": {"type": "object"},
        "permission_required": ["agent.write"],
        "timeout_seconds": 60,
        "rate_limit": {"per_user": 30, "per_agent": 200, "global": 1000},
        "implementation": {"type": "internal_function", "endpoint": "workspace.shell.exec"},
        "status": "active",
    },
    {
        "id": "web.fetch",
        "version": "1.0.0",
        "name": "网页抓取",
        "description": "HTTP GET 拉取网页正文（对标 WebFetch；URL 前缀白名单）",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["url"],
        },
        "output_schema": {"type": "object"},
        "permission_required": [],
        "timeout_seconds": 30,
        "rate_limit": {"per_user": 30, "per_agent": 200, "global": 2000},
        "implementation": {"type": "internal_function", "endpoint": "workspace.web.fetch"},
        "status": "active",
    },
    {
        "id": "web.search",
        "version": "1.0.0",
        "name": "网页搜索",
        "description": (
            "调用百度千帆 AI Search 检索全网实时信息，返回标题/摘要/链接"
            "（对标 WebSearch）"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词或自然语言问题"},
                "top_k": {
                    "type": "integer",
                    "description": "返回网页条数，最大 50",
                },
                "search_recency_filter": {
                    "type": "string",
                    "enum": ["week", "month", "semiyear", "year"],
                    "description": "按网页发布时间筛选",
                },
                "allowed_sites": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "仅搜索指定站点",
                },
                "block_websites": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "屏蔽站点列表",
                },
                "edition": {
                    "type": "string",
                    "enum": ["standard", "lite"],
                    "description": "搜索版本，lite 时延更低",
                },
            },
            "required": ["query"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "results": {"type": "array"},
                "total": {"type": "integer"},
            },
        },
        "permission_required": [],
        "timeout_seconds": 30,
        "rate_limit": {"per_user": 30, "per_agent": 300, "global": 3000},
        "implementation": {
            "type": "internal_function",
            "endpoint": "baidu.web.search",
        },
        "status": "active",
    },
]

TOOLS = TOOLS + WORKSPACE_TOOLS

# MCP / agent.spawn / fs.apply_patch 等 catalog 驱动种子
try:
    from agent_factory.core.tool_catalog import catalog_registry_seeds

    _seeded_ids = {t["id"] for t in TOOLS}
    TOOLS = TOOLS + catalog_registry_seeds(skip_ids=frozenset(_seeded_ids))
except Exception as exc:
    logger.warning("catalog_registry_seeds skipped: %s", exc)

SYSTEM_CONFIG = [
    ("runspec_schema_version_current", "1"),
    ("degradation.default_level", "0"),
    ("audit.default_level", "minimal"),
    ("audit.default_retain_days", "90"),
    ("session.default_timeout_minutes", "30"),
    ("mau.threshold.default", "5"),
    ("agent.max_versions_keep", "10"),
    ("skill.max_versions_keep", "50"),
]


async def _ensure_roles(session: AsyncSession) -> None:
    for role_id, name, desc in ROLES:
        result = await session.execute(select(Role).where(Role.id == role_id))
        if result.scalar_one_or_none() is None:
            session.add(Role(id=role_id, name=name, description=desc))
            logger.info("Inserted role: %s", role_id)
        else:
            logger.info("Role already exists: %s", role_id)
    await session.flush()


async def _ensure_permissions(session: AsyncSession) -> None:
    for perm_id, name, resource, action in PERMISSIONS:
        result = await session.execute(
            select(Permission).where(Permission.id == perm_id)
        )
        if result.scalar_one_or_none() is None:
            session.add(
                Permission(id=perm_id, name=name, resource=resource, action=action)
            )
            logger.info("Inserted permission: %s", perm_id)
        else:
            logger.info("Permission already exists: %s", perm_id)
    await session.flush()


async def _ensure_role_permissions(session: AsyncSession) -> None:
    for role_id, perm_id in ROLE_PERMISSIONS:
        result = await session.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == perm_id,
            )
        )
        if result.scalar_one_or_none() is None:
            session.add(RolePermission(role_id=role_id, permission_id=perm_id))
            logger.info("Linked %s -> %s", role_id, perm_id)
    await session.flush()


async def _ensure_platform_policy(session: AsyncSession) -> None:
    result = await session.execute(
        select(PlatformPolicy).where(
            PlatformPolicy.lineage_id == PLATFORM_POLICY["lineage_id"]
        )
    )
    if result.scalar_one_or_none() is None:
        session.add(
            PlatformPolicy(
                lineage_id=PLATFORM_POLICY["lineage_id"],
                version=PLATFORM_POLICY["version"],
                prompt=PLATFORM_POLICY["prompt"],
                enabled=PLATFORM_POLICY["enabled"],
            )
        )
        logger.info("Inserted platform policy: default")
    else:
        logger.info("Platform policy already exists: default")
    await session.flush()


async def _ensure_tools(session: AsyncSession) -> None:
    for tool in TOOLS:
        result = await session.execute(
            select(Tool).where(
                Tool.id == tool["id"],
                Tool.version == tool["version"],
            )
        )
        if result.scalar_one_or_none() is None:
            session.add(
                Tool(
                    id=tool["id"],
                    version=tool["version"],
                    name=tool["name"],
                    description=tool["description"],
                    input_schema=tool["input_schema"],
                    output_schema=tool["output_schema"],
                    permission_required=tool["permission_required"],
                    timeout_seconds=tool["timeout_seconds"],
                    rate_limit=tool["rate_limit"],
                    implementation=tool["implementation"],
                    status=tool["status"],
                )
            )
            logger.info("Inserted tool: %s@%s", tool["id"], tool["version"])
        else:
            logger.info("Tool already exists: %s@%s", tool["id"], tool["version"])
    await session.flush()


async def _ensure_system_config(session: AsyncSession) -> None:
    for key, value in SYSTEM_CONFIG:
        result = await session.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        if result.scalar_one_or_none() is None:
            session.add(SystemConfig(key=key, value=value))
            logger.info("Inserted system config: %s", key)
        else:
            logger.info("System config already exists: %s", key)
    await session.flush()


async def init_db() -> None:
    settings = get_settings()
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=0,
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # type: ignore[call-overload]

    async with async_session() as session:
        async with session.begin():
            await _ensure_roles(session)
            await _ensure_permissions(session)
            await _ensure_role_permissions(session)
            await _ensure_platform_policy(session)
            await _ensure_tools(session)
            await _ensure_system_config(session)

    await engine.dispose()
    logger.info("Initialization complete.")


if __name__ == "__main__":
    asyncio.run(init_db())
