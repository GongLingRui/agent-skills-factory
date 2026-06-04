"""Tests for workspace sandbox tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent_factory.config import Settings
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.tool_gateway import ToolGateway
from agent_factory.services.workspace_tools import (
    handle_fs_edit,
    handle_fs_glob,
    handle_fs_grep,
    handle_fs_read,
    handle_fs_write,
)


@pytest.fixture
def ws(tmp_path: Path) -> Settings:
    return Settings.model_construct(
        WORKSPACE_TOOLS_ENABLED=True,
        WORKSPACE_ROOT=str(tmp_path),
        SHELL_EXEC_ENABLED=True,
        WEB_FETCH_ENABLED=True,
        WEB_FETCH_URL_PREFIXES="https://",
    )


def test_fs_write_read_edit(ws: Settings, tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    handle_fs_write(
        {"file_path": "hello.txt", "content": "line1\nline2\nline3\n"},
        settings=ws,
    )
    out = handle_fs_read({"file_path": str(target)}, settings=ws)
    assert "line2" in out["content"]
    handle_fs_edit(
        {
            "file_path": "hello.txt",
            "old_string": "line2",
            "new_string": "LINE2",
        },
        settings=ws,
    )
    out2 = handle_fs_read({"file_path": "hello.txt"}, settings=ws)
    assert "LINE2" in out2["content"]


def test_fs_glob_and_grep(ws: Settings, tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def foo():\n    return 42\n", encoding="utf-8")
    glob_out = handle_fs_glob({"pattern": "**/*.py"}, settings=ws)
    assert any("main.py" in m for m in glob_out["matches"])
    grep_out = handle_fs_grep({"pattern": "return 42", "path": "src"}, settings=ws)
    assert grep_out["matches"]


def test_path_traversal_blocked(ws: Settings) -> None:
    with pytest.raises(AgentFactoryException) as exc:
        handle_fs_read({"file_path": "/etc/passwd"}, settings=ws)
    assert exc.value.code == "FORBIDDEN"


def test_tool_gateway_fs_read(ws: Settings, tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("ok", encoding="utf-8")
    gw = ToolGateway()
    with patch(
        "agent_factory.services.tool_gateway.get_settings",
        return_value=ws,
    ):
        out = gw.validate_and_run(
            tool_id="fs.read",
            params={"file_path": "a.txt"},
            allowed_tools=["fs.read"],
            retrieval_scopes=[],
        )
    assert out["content"] == "ok"


@pytest.mark.asyncio
async def test_tool_gateway_web_fetch(ws: Settings) -> None:
    gw = ToolGateway()
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/plain"}
    mock_resp.text = "hello web"

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url: str):
            assert url.startswith("https://")
            return mock_resp

    with (
        patch(
            "agent_factory.services.tool_gateway.get_settings",
            return_value=ws,
        ),
        patch(
            "agent_factory.services.workspace_tools.httpx.AsyncClient",
            return_value=_Client(),
        ),
    ):
        out = await gw.validate_and_run_async(
            db=AsyncMock(),
            tool_id="web.fetch",
            params={"url": "https://example.com/page"},
            allowed_tools=["web.fetch"],
            retrieval_scopes=[],
        )
    assert out["content"] == "hello web"
