"""OpenClaw-style tool catalog: descriptors, groups, registry seeds, presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolDescriptor:
    id: str
    name: str
    group: str
    description: str
    openclaw_alias: str = ""
    implemented: bool = False
    read_only: bool = False
    default_for_studio: bool = False
    profiles: tuple[str, ...] = ()
    mcp_server: str | None = None
    mcp_tool: str | None = None
    permission_required: list[str] | None = None


TOOL_GROUPS: dict[str, str] = {
    "filesystem": "文件系统",
    "runtime": "运行时",
    "web": "Web",
    "enterprise": "企业知识",
    "feishu": "飞书",
    "mcp_context7": "MCP · Context7 文档",
    "mcp_playwright": "MCP · Playwright 浏览器",
    "agents": "Agent / 子代理",
    "memory": "记忆",
    "session": "会话",
    "ui": "UI",
    "automation": "自动化",
    "media": "媒体",
    "messaging": "消息",
    "nodes": "Nodes",
}

# OpenClaw group:* expansion (tool-policy-shared parity)
TOOL_GROUP_MEMBERS: dict[str, list[str]] = {
    "group:openclaw": [],  # filled after TOOL_CATALOG defined
    "group:filesystem": [
        "fs.read",
        "fs.write",
        "fs.edit",
        "fs.apply_patch",
        "fs.glob",
        "fs.grep",
    ],
    "group:runtime": ["shell.exec", "shell.process", "runtime.code_execution"],
    "group:web": ["web.search", "web.fetch", "web.x_search"],
    "group:enterprise": [
        "kb.search",
        "doc.extract",
        "read_reference",
        "risk.rule_check",
    ],
    "group:feishu": ["feishu.doc"],
    "group:mcp_context7": [
        "mcp.context7.resolve_library_id",
        "mcp.context7.query_docs",
    ],
    "group:mcp_playwright": [
        "mcp.playwright.navigate",
        "mcp.playwright.snapshot",
        "mcp.playwright.click",
        "mcp.playwright.fill",
    ],
    "group:agents": [
        "agent.spawn",
        "agent.list",
        "agents.update_plan",
        "sessions.spawn",
        "sessions.subagents",
    ],
    "group:memory": ["memory.search", "memory.get"],
    "group:sessions": [
        "sessions.list",
        "sessions.history",
        "sessions.send",
        "sessions.spawn",
        "sessions.yield",
        "sessions.subagents",
        "sessions.status",
    ],
    "group:ui": ["ui.browser", "ui.canvas"],
    "group:automation": [
        "automation.cron",
        "automation.gateway",
        "automation.heartbeat_respond",
    ],
    "group:media": [
        "media.image",
        "media.image_generate",
        "media.music_generate",
        "media.video_generate",
        "media.pdf",
        "media.tts",
    ],
    "group:messaging": ["messaging.message"],
    "group:nodes": ["nodes.manage"],
}


def _desc(
    id: str,
    name: str,
    group: str,
    description: str,
    **kwargs: Any,
) -> ToolDescriptor:
    return ToolDescriptor(id, name, group, description, **kwargs)


TOOL_CATALOG: tuple[ToolDescriptor, ...] = (
    # filesystem
    _desc(
        "fs.read",
        "读取文件",
        "filesystem",
        "读取工作区文本文件（对标 read）",
        openclaw_alias="read",
        implemented=True,
        read_only=True,
        profiles=("coding", "full"),
    ),
    _desc(
        "fs.write",
        "写入文件",
        "filesystem",
        "创建或覆盖文件（对标 write）",
        openclaw_alias="write",
        implemented=True,
    ),
    _desc(
        "fs.edit",
        "编辑文件",
        "filesystem",
        "定点替换编辑（对标 edit）",
        openclaw_alias="edit",
        implemented=True,
    ),
    _desc(
        "fs.apply_patch",
        "应用补丁",
        "filesystem",
        "应用 unified diff 补丁（对标 apply_patch）",
        openclaw_alias="apply_patch",
        implemented=True,
    ),
    _desc("fs.glob", "Glob", "filesystem", "按模式列出文件", openclaw_alias="glob", implemented=True, read_only=True),
    _desc("fs.grep", "Grep", "filesystem", "内容搜索", openclaw_alias="grep", implemented=True, read_only=True),
    # runtime
    _desc(
        "shell.exec",
        "Shell",
        "runtime",
        "执行 shell 命令（对标 exec）",
        openclaw_alias="exec",
        implemented=True,
    ),
    _desc(
        "shell.process",
        "进程管理",
        "runtime",
        "查看/管理后台进程（对标 process）",
        openclaw_alias="process",
        implemented=True,
    ),
    _desc(
        "runtime.code_execution",
        "代码沙箱",
        "runtime",
        "隔离环境代码执行（对标 code_execution）",
        openclaw_alias="code_execution",
        implemented=True,
    ),
    # web
    _desc(
        "web.search",
        "网页搜索",
        "web",
        "百度千帆全网搜索（对标 web_search）",
        openclaw_alias="web_search",
        implemented=True,
        read_only=True,
        default_for_studio=True,
    ),
    _desc(
        "web.fetch",
        "网页抓取",
        "web",
        "HTTP GET 获取页面（对标 web_fetch）",
        openclaw_alias="web_fetch",
        implemented=True,
        read_only=True,
    ),
    _desc(
        "web.x_search",
        "X 搜索",
        "web",
        "搜索 X/Twitter 帖子（对标 x_search）",
        openclaw_alias="x_search",
        implemented=True,
        read_only=True,
    ),
    # enterprise
    _desc(
        "kb.search",
        "知识库检索",
        "enterprise",
        "内部知识库检索",
        openclaw_alias="kb.search",
        implemented=True,
        read_only=True,
        default_for_studio=True,
    ),
    _desc(
        "doc.extract",
        "文档解析",
        "enterprise",
        "解析用户上传附件",
        openclaw_alias="doc.extract",
        implemented=True,
        read_only=True,
        default_for_studio=True,
    ),
    _desc(
        "read_reference",
        "Skill 引用",
        "enterprise",
        "读取 Skill 包 reference",
        openclaw_alias="read_reference",
        implemented=True,
        read_only=True,
        default_for_studio=True,
    ),
    _desc(
        "risk.rule_check",
        "规则扫描",
        "enterprise",
        "条款风险规则扫描",
        implemented=True,
        read_only=True,
    ),
    _desc(
        "feishu.doc",
        "飞书云文档",
        "feishu",
        (
            "飞书云文档读写：read/write/append/create/list_blocks。"
            "从 URL /docx/TOKEN 提取 doc_token；create 会自动给当前飞书用户编辑权限。"
        ),
        openclaw_alias="feishu_doc",
        implemented=True,
    ),
    # mcp context7
    _desc(
        "mcp.context7.resolve_library_id",
        "Context7 库 ID",
        "mcp_context7",
        "解析库名到 Context7 library ID",
        openclaw_alias="resolve-library-id",
        implemented=True,
        read_only=True,
        mcp_server="context7",
        mcp_tool="resolve-library-id",
    ),
    _desc(
        "mcp.context7.query_docs",
        "Context7 文档",
        "mcp_context7",
        "查询库文档与示例",
        openclaw_alias="query-docs",
        implemented=True,
        read_only=True,
        mcp_server="context7",
        mcp_tool="query-docs",
    ),
    # mcp playwright
    _desc(
        "mcp.playwright.navigate",
        "浏览器导航",
        "mcp_playwright",
        "打开 URL",
        openclaw_alias="browser_navigate",
        implemented=True,
        mcp_server="playwright",
        mcp_tool="browser_navigate",
    ),
    _desc(
        "mcp.playwright.snapshot",
        "页面快照",
        "mcp_playwright",
        "获取可访问性树/页面结构",
        openclaw_alias="browser_snapshot",
        implemented=True,
        read_only=True,
        mcp_server="playwright",
        mcp_tool="browser_snapshot",
    ),
    _desc(
        "mcp.playwright.click",
        "点击元素",
        "mcp_playwright",
        "点击页面元素",
        openclaw_alias="browser_click",
        implemented=True,
        mcp_server="playwright",
        mcp_tool="browser_click",
    ),
    _desc(
        "mcp.playwright.fill",
        "填写表单",
        "mcp_playwright",
        "向输入框填写文本",
        openclaw_alias="browser_fill",
        implemented=True,
        mcp_server="playwright",
        mcp_tool="browser_fill",
    ),
    # agents
    _desc(
        "agent.spawn",
        "子 Agent",
        "agents",
        "派生子 Agent 执行独立任务并返回结果（对标 sessions_spawn / Task）",
        openclaw_alias="sessions_spawn",
        implemented=True,
    ),
    _desc(
        "agent.list",
        "Agent 列表",
        "agents",
        "列出可用 Agent App（对标 agents_list）",
        openclaw_alias="agents_list",
        implemented=True,
        read_only=True,
    ),
    _desc(
        "agents.update_plan",
        "更新计划",
        "agents",
        "更新 Agent 任务计划步骤（对标 update_plan）",
        openclaw_alias="update_plan",
        implemented=True,
    ),
    # memory
    _desc(
        "memory.search",
        "记忆搜索",
        "memory",
        "语义/FTS 搜索 MEMORY.md 与会话记忆（对标 memory_search）",
        openclaw_alias="memory_search",
        implemented=True,
        read_only=True,
    ),
    _desc(
        "memory.get",
        "读取记忆",
        "memory",
        "读取记忆 markdown 片段（对标 memory_get）",
        openclaw_alias="memory_get",
        implemented=True,
        read_only=True,
    ),
    # sessions
    _desc(
        "sessions.list",
        "会话列表",
        "session",
        "列出用户会话（对标 sessions_list）",
        openclaw_alias="sessions_list",
        implemented=True,
        read_only=True,
    ),
    _desc(
        "sessions.history",
        "会话历史",
        "session",
        "读取会话 transcript（对标 sessions_history）",
        openclaw_alias="sessions_history",
        implemented=True,
        read_only=True,
    ),
    _desc(
        "sessions.send",
        "发送消息",
        "session",
        "向另一会话发消息并可选等待回复（对标 sessions_send）",
        openclaw_alias="sessions_send",
        implemented=True,
    ),
    _desc(
        "sessions.spawn",
        "创建子会话",
        "session",
        "创建子 Agent 会话执行任务（对标 sessions_spawn）",
        openclaw_alias="sessions_spawn",
        implemented=True,
    ),
    _desc(
        "sessions.yield",
        "Yield",
        "session",
        "结束 turn 并传递 yield 消息（对标 sessions_yield）",
        openclaw_alias="sessions_yield",
        implemented=True,
    ),
    _desc(
        "sessions.subagents",
        "子代理列表",
        "session",
        "列出当前会话下的 subagent runs（对标 subagents）",
        openclaw_alias="subagents",
        implemented=True,
        read_only=True,
    ),
    _desc(
        "sessions.status",
        "会话状态",
        "session",
        "查询会话元数据与运行状态（对标 session_status）",
        openclaw_alias="session_status",
        implemented=True,
        read_only=True,
    ),
    # ui
    _desc(
        "ui.browser",
        "浏览器",
        "ui",
        "统一 browser 工具（Playwright MCP，对标 browser）",
        openclaw_alias="browser",
        implemented=True,
    ),
    _desc(
        "ui.canvas",
        "Canvas",
        "ui",
        "Canvas/A2UI 控制（对标 canvas）",
        openclaw_alias="canvas",
        implemented=True,
    ),
    # automation
    _desc(
        "automation.cron",
        "定时任务",
        "automation",
        "Cron 调度 CRUD（对标 cron）",
        openclaw_alias="cron",
        implemented=True,
    ),
    _desc(
        "automation.gateway",
        "Gateway",
        "automation",
        "Gateway 状态与配置查询（对标 gateway）",
        openclaw_alias="gateway",
        implemented=True,
        read_only=True,
    ),
    _desc(
        "automation.heartbeat_respond",
        "心跳响应",
        "automation",
        "记录 heartbeat 结果（对标 heartbeat_respond）",
        openclaw_alias="heartbeat_respond",
        implemented=True,
    ),
    # messaging
    _desc(
        "messaging.message",
        "发送消息",
        "messaging",
        "向会话/渠道发送消息（对标 message）",
        openclaw_alias="message",
        implemented=True,
    ),
    # nodes
    _desc(
        "nodes.manage",
        "Nodes",
        "nodes",
        "Nodes + 设备管理（对标 nodes）",
        openclaw_alias="nodes",
        implemented=True,
    ),
    # media
    _desc(
        "media.image",
        "图像理解",
        "media",
        "VLM 图像描述（对标 image）",
        openclaw_alias="image",
        implemented=True,
        read_only=True,
    ),
    _desc(
        "media.image_generate",
        "图像生成",
        "media",
        "图像生成（对标 image_generate）",
        openclaw_alias="image_generate",
        implemented=True,
    ),
    _desc(
        "media.music_generate",
        "音乐生成",
        "media",
        "音乐生成（对标 music_generate）",
        openclaw_alias="music_generate",
        implemented=True,
    ),
    _desc(
        "media.video_generate",
        "视频生成",
        "media",
        "视频生成（对标 video_generate）",
        openclaw_alias="video_generate",
        implemented=True,
    ),
    _desc(
        "media.pdf",
        "PDF 分析",
        "media",
        "提取并分析 PDF（对标 pdf）",
        openclaw_alias="pdf",
        implemented=True,
        read_only=True,
    ),
    _desc(
        "media.tts",
        "文字转语音",
        "media",
        "TTS 语音合成（对标 tts）",
        openclaw_alias="tts",
        implemented=True,
    ),
)

TOOL_BY_ID: dict[str, ToolDescriptor] = {t.id: t for t in TOOL_CATALOG}

IMPLEMENTED_TOOL_IDS: frozenset[str] = frozenset(
    t.id for t in TOOL_CATALOG if t.implemented
)

READ_ONLY_TOOL_IDS: frozenset[str] = frozenset(
    t.id for t in TOOL_CATALOG if t.implemented and t.read_only
)

STUDIO_DEFAULT_TOOL_IDS: list[str] = [
    t.id for t in TOOL_CATALOG if t.default_for_studio
]

# OpenClaw-style presets (align tool-catalog.ts profiles)
TOOL_PRESETS: dict[str, dict[str, Any]] = {
    "minimal": {
        "label": "精简",
        "description": "仅企业知识（OpenClaw minimal）",
        "tools": ["kb.search", "doc.extract", "read_reference"],
    },
    "coding": {
        "label": "代码开发",
        "description": "文件系统 + Shell + Web + Memory + Sessions + Context7（OpenClaw coding）",
        "tools": [
            "group:filesystem",
            "group:runtime",
            "group:web",
            "group:memory",
            "group:sessions",
            "group:mcp_context7",
            "read_reference",
        ],
    },
    "messaging": {
        "label": "企业知识",
        "description": "知识库 + 搜索 + 子 Agent",
        "tools": [
            "group:enterprise",
            "web.search",
            "agent.spawn",
            "agent.list",
        ],
    },
    "enterprise": {
        "label": "企业知识+",
        "description": "企业知识 + 规则扫描",
        "tools": ["group:enterprise"],
    },
    "web": {
        "label": "网页检索",
        "description": "搜索 + 抓取 + Context7",
        "tools": ["group:web", "group:mcp_context7", "read_reference"],
    },
    "browser": {
        "label": "浏览器自动化",
        "description": "Playwright MCP + 网页工具",
        "tools": ["group:web", "group:mcp_playwright"],
    },
    "agents": {
        "label": "多 Agent",
        "description": "子 Agent 编排 + 企业知识",
        "tools": ["group:agents", "group:enterprise"],
    },
    "full": {
        "label": "全量（已实现）",
        "description": "所有已实现的内置工具（OpenClaw full profile）",
        "tools": ["group:openclaw"],
    },
    "openclaw": {
        "label": "OpenClaw 完整",
        "description": "Memory + Sessions + UI + Automation + Media + Coding",
        "tools": [
            "group:memory",
            "group:sessions",
            "group:ui",
            "group:messaging",
            "group:nodes",
            "group:automation",
            "group:media",
            "group:agents",
            "group:filesystem",
            "group:runtime",
            "group:web",
            "group:mcp_context7",
            "group:mcp_playwright",
            "group:enterprise",
        ],
    },
}

# Populate group:openclaw with all implemented tool ids
TOOL_GROUP_MEMBERS["group:openclaw"] = sorted(
    t.id for t in TOOL_CATALOG if t.implemented  # type: ignore[name-defined]
)


def expand_tool_groups(tool_ids: list[str]) -> list[str]:
    """Expand group:* entries to concrete tool ids (OpenClaw expandToolGroups)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in tool_ids:
        tid = str(raw).strip()
        if not tid:
            continue
        if tid.startswith("group:"):
            for member in TOOL_GROUP_MEMBERS.get(tid, []):
                if member not in seen:
                    seen.add(member)
                    out.append(member)
            continue
        if tid not in seen:
            seen.add(tid)
            out.append(tid)
    return out


def catalog_for_api(*, settings: Any | None = None) -> dict[str, Any]:
    """Serialize catalog + presets for Studio UI."""
    from agent_factory.config import get_settings

    cfg = settings or get_settings()
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in TOOL_CATALOG:
        entry = {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "openclaw_alias": t.openclaw_alias,
            "implemented": t.implemented,
            "available": t.implemented and _tool_available(t, cfg),
        }
        groups.setdefault(t.group, []).append(entry)
    presets = [
        {
            "id": pid,
            "label": meta["label"],
            "description": meta["description"],
            "tools": meta["tools"],
            "tools_expanded": expand_tool_groups(meta["tools"]),
        }
        for pid, meta in TOOL_PRESETS.items()
    ]
    default_expanded = expand_tool_groups(list(STUDIO_DEFAULT_TOOL_IDS))
    return {
        "groups": [{"id": gid, "label": TOOL_GROUPS.get(gid, gid), "tools": groups.get(gid, [])} for gid in TOOL_GROUPS],
        "presets": presets,
        "default_tools": list(STUDIO_DEFAULT_TOOL_IDS),
        "default_tools_expanded": default_expanded,
    }


def _tool_available(t: ToolDescriptor, settings: Any) -> bool:
    if not t.implemented:
        return False
    if t.id.startswith("mcp.context7."):
        return bool(getattr(settings, "MCP_CONTEXT7_ENABLED", True))
    if t.id.startswith("mcp.playwright."):
        return bool(getattr(settings, "MCP_PLAYWRIGHT_ENABLED", True))
    if t.id == "shell.exec":
        return bool(getattr(settings, "SHELL_EXEC_ENABLED", True))
    if t.id == "web.search":
        return bool(getattr(settings, "WEB_SEARCH_ENABLED", True))
    if t.id == "web.x_search":
        return bool(
            getattr(settings, "WEB_X_SEARCH_ENABLED", True)
            or getattr(settings, "WEB_SEARCH_ENABLED", True)
        )
    if t.id.startswith("messaging."):
        return bool(getattr(settings, "MESSAGING_TOOLS_ENABLED", True))
    if t.id.startswith("nodes."):
        return bool(getattr(settings, "NODES_TOOLS_ENABLED", True))
    if t.id == "web.fetch":
        return bool(getattr(settings, "WEB_FETCH_ENABLED", True))
    if t.id.startswith("memory."):
        return bool(getattr(settings, "MEMORY_TOOLS_ENABLED", True))
    if t.id.startswith("sessions."):
        return bool(getattr(settings, "SESSIONS_TOOLS_ENABLED", True))
    if t.id.startswith("ui."):
        return bool(getattr(settings, "UI_TOOLS_ENABLED", True))
    if t.id.startswith("automation."):
        return bool(getattr(settings, "AUTOMATION_TOOLS_ENABLED", True))
    if t.id.startswith("media."):
        return bool(getattr(settings, "MEDIA_TOOLS_ENABLED", True))
    if t.id == "runtime.code_execution":
        return bool(getattr(settings, "CODE_EXECUTION_ENABLED", True))
    if t.id == "shell.process":
        return bool(getattr(settings, "WORKSPACE_TOOLS_ENABLED", True))
    if t.id.startswith("fs.") or t.id == "shell.exec":
        return bool(getattr(settings, "WORKSPACE_TOOLS_ENABLED", True))
    return True


def input_schema_for_tool(tool_id: str) -> dict[str, Any]:
    """Minimal JSON Schema for Tool Registry seed."""
    schemas: dict[str, dict[str, Any]] = {
        "fs.read": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}},
            "required": ["file_path"],
        },
        "fs.write": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["file_path", "content"],
        },
        "fs.edit": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
        "fs.apply_patch": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "patch": {"type": "string"}},
            "required": ["file_path", "patch"],
        },
        "agent.spawn": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "目标 Agent ID"},
                "prompt": {"type": "string", "description": "子任务提示词"},
                "description": {"type": "string", "description": "任务简述（审计用）"},
            },
            "required": ["agent_id", "prompt"],
        },
        "agent.list": {"type": "object", "properties": {"query": {"type": "string"}}},
        "feishu.doc": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "append", "create", "list_blocks"],
                    "description": "文档操作类型",
                },
                "doc_token": {
                    "type": "string",
                    "description": "文档 token（可从 https://xxx.feishu.cn/docx/TOKEN 提取）",
                },
                "content": {
                    "type": "string",
                    "description": "Markdown 内容（write 替换全文，append 追加到末尾）",
                },
                "title": {"type": "string", "description": "新建文档标题（create）"},
                "folder_token": {
                    "type": "string",
                    "description": "目标文件夹 token（create，可选）",
                },
                "grant_to_requester": {
                    "type": "boolean",
                    "description": "create 时是否给当前飞书用户 edit 权限（默认 true）",
                },
            },
            "required": ["action"],
        },
        "mcp.context7.resolve_library_id": {
            "type": "object",
            "properties": {"libraryName": {"type": "string"}, "query": {"type": "string"}},
            "required": ["libraryName", "query"],
        },
        "mcp.context7.query_docs": {
            "type": "object",
            "properties": {"libraryId": {"type": "string"}, "query": {"type": "string"}},
            "required": ["libraryId", "query"],
        },
        "mcp.playwright.navigate": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        "mcp.playwright.snapshot": {"type": "object", "properties": {}},
        "mcp.playwright.click": {
            "type": "object",
            "properties": {"ref": {"type": "string"}, "element": {"type": "string"}},
            "required": ["ref"],
        },
        "mcp.playwright.fill": {
            "type": "object",
            "properties": {"ref": {"type": "string"}, "text": {"type": "string"}},
            "required": ["ref", "text"],
        },
        "memory.search": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "maxResults": {"type": "integer"},
                "minScore": {"type": "number"},
                "corpus": {"type": "string", "enum": ["memory", "sessions", "all", "wiki"]},
            },
            "required": ["query"],
        },
        "memory.get": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "from": {"type": "integer"},
                "lines": {"type": "integer"},
                "corpus": {"type": "string"},
            },
            "required": ["path"],
        },
        "sessions.list": {
            "type": "object",
            "properties": {
                "kinds": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"},
                "search": {"type": "string"},
                "label": {"type": "string"},
                "agentId": {"type": "string"},
            },
        },
        "sessions.history": {
            "type": "object",
            "properties": {
                "sessionKey": {"type": "string"},
                "label": {"type": "string"},
                "messageLimit": {"type": "integer"},
            },
        },
        "sessions.send": {
            "type": "object",
            "properties": {
                "sessionKey": {"type": "string"},
                "label": {"type": "string"},
                "message": {"type": "string"},
                "timeoutSeconds": {"type": "number"},
            },
            "required": ["message"],
        },
        "sessions.spawn": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "taskName": {"type": "string"},
                "label": {"type": "string"},
                "agentId": {"type": "string"},
                "runtime": {"type": "string"},
                "waitForReply": {"type": "boolean"},
            },
            "required": ["task"],
        },
        "sessions.yield": {
            "type": "object",
            "properties": {"message": {"type": "string"}, "runId": {"type": "string"}},
            "required": ["message"],
        },
        "sessions.subagents": {"type": "object", "properties": {}},
        "sessions.status": {
            "type": "object",
            "properties": {"sessionKey": {"type": "string"}},
        },
        "ui.browser": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "url": {"type": "string"},
                "ref": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["action"],
        },
        "ui.canvas": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "url": {"type": "string"},
                "title": {"type": "string"},
                "payload": {"type": "object"},
            },
            "required": ["action"],
        },
        "automation.cron": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "jobId": {"type": "string"},
                "name": {"type": "string"},
                "schedule": {"type": "object"},
                "payload": {"type": "object"},
            },
        },
        "automation.gateway": {
            "type": "object",
            "properties": {"action": {"type": "string"}, "toolId": {"type": "string"}},
        },
        "media.image": {
            "type": "object",
            "properties": {
                "imagePath": {"type": "string"},
                "prompt": {"type": "string"},
                "model": {"type": "string"},
            },
            "required": ["imagePath"],
        },
        "media.image_generate": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}, "action": {"type": "string"}},
        },
        "shell.process": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "processId": {"type": "string"},
                "command": {"type": "string"},
            },
        },
        "runtime.code_execution": {
            "type": "object",
            "properties": {"task": {"type": "string"}, "timeoutSeconds": {"type": "integer"}},
            "required": ["task"],
        },
        "web.x_search": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "maxResults": {"type": "integer"}},
            "required": ["query"],
        },
        "messaging.message": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "message": {"type": "string"},
                "channel": {"type": "string"},
            },
        },
        "automation.heartbeat_respond": {
            "type": "object",
            "properties": {
                "outcome": {"type": "string"},
                "notify": {"type": "boolean"},
                "summary": {"type": "string"},
                "notificationText": {"type": "string"},
            },
            "required": ["outcome", "notify", "summary"],
        },
        "nodes.manage": {
            "type": "object",
            "properties": {"action": {"type": "string"}, "node": {"type": "string"}},
            "required": ["action"],
        },
        "agents.update_plan": {
            "type": "object",
            "properties": {
                "explanation": {"type": "string"},
                "plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "string"},
                            "status": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["plan"],
        },
        "media.music_generate": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}, "lyrics": {"type": "string"}, "action": {"type": "string"}},
        },
        "media.video_generate": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}, "action": {"type": "string"}},
        },
        "media.pdf": {
            "type": "object",
            "properties": {
                "pdf": {"type": "string", "description": "工作区内 PDF 路径"},
                "file_id": {"type": "string", "description": "已上传文件 ID"},
                "pdfs": {"type": "array", "items": {"type": "string"}},
                "pages": {"type": "string", "description": "页码范围，如 1-5,1,3"},
                "prompt": {"type": "string"},
                "model": {"type": "string"},
                "extractOnly": {"type": "boolean"},
            },
        },
        "media.tts": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "channel": {"type": "string"},
                "timeoutMs": {"type": "integer"},
            },
            "required": ["text"],
        },
    }
    if tool_id in schemas:
        return schemas[tool_id]
    return {"type": "object", "properties": {}}


def registry_seed_entries() -> list[dict[str, Any]]:
    """Build init_db TOOL rows for catalog entries not already seeded."""
    return catalog_registry_seeds(skip_ids=frozenset())


def catalog_registry_seeds(*, skip_ids: frozenset[str]) -> list[dict[str, Any]]:
    """Registry rows for implemented tools missing from skip_ids."""
    out: list[dict[str, Any]] = []
    for t in TOOL_CATALOG:
        if not t.implemented or t.id in skip_ids:
            continue
        out.append(
            {
                "id": t.id,
                "version": "1.0.0",
                "name": t.name,
                "description": t.description,
                "input_schema": input_schema_for_tool(t.id),
                "output_schema": {"type": "object"},
                "permission_required": list(t.permission_required or []),
                "timeout_seconds": 30,
                "rate_limit": {"per_user": 60, "per_agent": 500, "global": 5000},
                "implementation": {
                    "type": "internal_function",
                    "endpoint": f"tool_catalog.{t.id}",
                },
                "status": "active",
            }
        )
    return out
