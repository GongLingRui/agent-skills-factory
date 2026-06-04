"""Tests for OpenClaw-style tool planner."""

from agent_factory.config import Settings
from agent_factory.core.tool_catalog import expand_tool_groups
from agent_factory.core.tool_planner import plan_tools_for_requirements, tools_for_preset


def test_expand_tool_groups():
    out = expand_tool_groups(["group:filesystem", "web.search"])
    assert "fs.read" in out
    assert "web.search" in out


def test_tools_for_preset_coding():
    tools = tools_for_preset("coding")
    assert tools is not None
    assert "fs.read" in tools
    assert "shell.exec" in tools


def test_plan_tools_auto_coding_keywords():
    settings = Settings.model_construct(
        WORKSPACE_TOOLS_ENABLED=True,
        SHELL_EXEC_ENABLED=True,
        WEB_SEARCH_ENABLED=True,
        MCP_CONTEXT7_ENABLED=True,
    )
    tools = plan_tools_for_requirements(
        "帮我重构 backend 里的 Python pytest 测试",
        settings=settings,
    )
    assert "fs.grep" in tools or "fs.read" in tools


def test_plan_tools_respects_explicit_preset():
    settings = Settings.model_construct(
        WORKSPACE_TOOLS_ENABLED=True,
        WEB_SEARCH_ENABLED=True,
        WEB_FETCH_ENABLED=True,
        MCP_PLAYWRIGHT_ENABLED=True,
    )
    tools = plan_tools_for_requirements(
        "随便什么",
        preset="browser",
        settings=settings,
    )
    assert "mcp.playwright.navigate" in tools
