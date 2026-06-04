"""Tests for OpenClaw runtime tools (memory, sessions, automation, process)."""

from pathlib import Path

import pytest

from agent_factory.config import Settings
from agent_factory.core.tool_catalog import IMPLEMENTED_TOOL_IDS, expand_tool_groups
from agent_factory.services.memory_store import memory_agent_root, rebuild_memory_index, search_memory_files
from agent_factory.services.process_tools import handle_shell_process
from agent_factory.services.agent_cron_service import compute_next_run


def test_openclaw_tool_ids_registered():
    groups = expand_tool_groups(
        [
            "group:memory",
            "group:sessions",
            "group:ui",
            "group:automation",
            "group:media",
            "group:messaging",
            "group:nodes",
            "group:web",
            "group:agents",
        ]
    )
    for tid in groups:
        assert tid in IMPLEMENTED_TOOL_IDS, tid


def test_pdf_page_range_parser():
    from agent_factory.services.media_pdf_tts_tools import _parse_page_range

    assert _parse_page_range("1-3", 10) == [1, 2, 3]
    assert _parse_page_range("1,3,5-7", 10) == [1, 3, 5, 6, 7]


def test_catalog_includes_pdf_and_tts():
    assert "media.pdf" in IMPLEMENTED_TOOL_IDS
    assert "media.tts" in IMPLEMENTED_TOOL_IDS
    expanded = expand_tool_groups(["group:media"])
    assert "media.pdf" in expanded
    assert "media.tts" in expanded
    from agent_factory.services.agents_plan_tools import _parse_plan

    plan = _parse_plan(
        {
            "plan": [
                {"step": "Analyze", "status": "completed"},
                {"step": "Implement", "status": "in_progress"},
            ]
        }
    )
    assert len(plan) == 2


def test_memory_search_fts(tmp_path, monkeypatch):
    settings = Settings.model_construct(WORKSPACE_ROOT=str(tmp_path))
    monkeypatch.setattr(
        "agent_factory.services.memory_store.get_settings",
        lambda: settings,
    )
    root = memory_agent_root(user_id_hash="u1", agent_id="a1", settings=settings)
    (root / "memory").mkdir(exist_ok=True)
    (root / "memory" / "notes.md").write_text(
        "Python pytest refactoring backend services\n", encoding="utf-8"
    )
    rebuild_memory_index(root)
    hits = search_memory_files(root, "pytest python", max_results=5)
    assert hits
    assert any("notes.md" in h.path for h in hits)


def test_shell_process_submit_and_poll():
    settings = Settings.model_construct(
        WORKSPACE_TOOLS_ENABLED=True,
        WORKSPACE_ROOT=str(Path.cwd()),
    )
    started = handle_shell_process(
        {"action": "submit", "command": "echo hello_process_test"},
        settings=settings,
    )
    pid = started["processId"]
    polled = handle_shell_process(
        {"action": "poll", "processId": pid},
        settings=settings,
    )
    assert "running" in polled
    logs = handle_shell_process(
        {"action": "log", "processId": pid, "tail": 20},
        settings=settings,
    )
    assert isinstance(logs["lines"], list)


def test_cron_compute_next_run_every():
    nxt = compute_next_run({"kind": "every", "everyMs": 60000})
    assert nxt is not None
