"""Plan which tools an Agent should carry (OpenClaw-style planner)."""

from __future__ import annotations

import re
from typing import Any

from agent_factory.core.tool_catalog import (
    IMPLEMENTED_TOOL_IDS,
    STUDIO_DEFAULT_TOOL_IDS,
    TOOL_PRESETS,
    TOOL_BY_ID,
    _tool_available,
    expand_tool_groups,
)
from agent_factory.config import Settings, get_settings


def _normalize_ids(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        tid = str(item).strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
    return out


def tools_for_preset(preset_id: str | None) -> list[str] | None:
    if not preset_id:
        return None
    meta = TOOL_PRESETS.get(preset_id.strip().lower())
    if meta is None:
        return None
    return expand_tool_groups(list(meta["tools"]))


def plan_tools_for_requirements(
    requirements: str,
    *,
    preset: str | None = None,
    selected: list[str] | None = None,
    llm_allow: list[str] | None = None,
    settings: Settings | None = None,
) -> list[str]:
    """Return ordered unique tool ids for Agent/Skill binding."""
    cfg = settings or get_settings()

    if llm_allow:
        base = _filter_available(_normalize_ids(llm_allow), cfg)
        if base:
            return base

    preset_tools = tools_for_preset(preset)
    if preset_tools:
        base = _filter_available(_normalize_ids(preset_tools), cfg)
        if base:
            return base

    if selected:
        base = _filter_available(_normalize_ids(selected), cfg)
        if base:
            return base

    req = requirements.lower()
    tools: set[str] = set(_filter_available(STUDIO_DEFAULT_TOOL_IDS, cfg))

    coding_kw = (
        "代码",
        "编程",
        "python",
        "typescript",
        "react",
        "bug",
        "refactor",
        "仓库",
        "git",
        "测试",
        "pytest",
    )
    web_kw = ("搜索", "联网", "实时", "新闻", "资料", "查一下", "百度", "google")
    browser_kw = ("浏览器", "网页点击", "登录", "表单", "playwright", "自动化测试")
    agent_kw = ("子代理", "多 agent", "编排", "工作流", "协同")

    if any(k in req for k in coding_kw):
        tools.update(_filter_available(TOOL_PRESETS["coding"]["tools"], cfg))
    if any(k in req for k in web_kw):
        tools.update(_filter_available(TOOL_PRESETS["web"]["tools"], cfg))
    if any(k in req for k in browser_kw):
        tools.update(_filter_available(TOOL_PRESETS["browser"]["tools"], cfg))
    if any(k in req for k in agent_kw):
        tools.update(_filter_available(TOOL_PRESETS["agents"]["tools"], cfg))

    # 短剧/故事类仍偏企业知识 + 搜索
    if re.search(r"故事|剧本|短剧|小说|梗概", requirements):
        tools.update(_filter_available(TOOL_PRESETS["enterprise"]["tools"], cfg))
        tools.update(_filter_available(["web.search"], cfg))

    if not tools:
        tools.update(_filter_available(STUDIO_DEFAULT_TOOL_IDS, cfg))

    return sorted(tools)


def _filter_available(tool_ids: list[str], settings: Settings) -> list[str]:
    expanded = expand_tool_groups(tool_ids)
    out: list[str] = []
    for tid in expanded:
        if tid not in IMPLEMENTED_TOOL_IDS:
            continue
        desc = TOOL_BY_ID.get(tid)
        if desc is None:
            continue
        if not _tool_available(desc, settings):
            continue
        out.append(tid)
    return out
