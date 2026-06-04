"""Tests for ``scripts/local_env.py`` (sync CLI dotenv loading)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from local_env import dotenv_files_contain_admin_token, load_env_for_sync_scripts  # noqa: E402


@pytest.fixture
def fake_script(tmp_path: Path) -> Path:
    scripts = tmp_path / "backend" / "scripts"
    scripts.mkdir(parents=True)
    (tmp_path / "backend" / "scripts" / "sync_fake.py").write_text(
        "# placeholder", encoding="utf-8"
    )
    return scripts / "sync_fake.py"


def test_load_env_fills_when_shell_empty(monkeypatch: pytest.MonkeyPatch, fake_script: Path, tmp_path: Path) -> None:
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_API_TOKEN", "")
    (tmp_path / ".env").write_text(
        "ADMIN_API_TOKEN=from-root\n", encoding="utf-8"
    )
    load_env_for_sync_scripts(fake_script)
    assert os.environ.get("ADMIN_API_TOKEN") == "from-root"


def test_backend_env_overrides_root(monkeypatch: pytest.MonkeyPatch, fake_script: Path, tmp_path: Path) -> None:
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    (tmp_path / ".env").write_text("ADMIN_API_TOKEN=root\n", encoding="utf-8")
    backend = tmp_path / "backend"
    (backend / ".env").write_text("ADMIN_API_TOKEN=backend\n", encoding="utf-8")
    load_env_for_sync_scripts(fake_script)
    assert os.environ.get("ADMIN_API_TOKEN") == "backend"


def test_nonempty_shell_wins(monkeypatch: pytest.MonkeyPatch, fake_script: Path, tmp_path: Path) -> None:
    monkeypatch.setenv("ADMIN_API_TOKEN", "shell")
    (tmp_path / ".env").write_text("ADMIN_API_TOKEN=file\n", encoding="utf-8")
    load_env_for_sync_scripts(fake_script)
    assert os.environ.get("ADMIN_API_TOKEN") == "shell"


def test_dotenv_files_contain_admin_token(fake_script: Path, tmp_path: Path) -> None:
    assert dotenv_files_contain_admin_token(fake_script) is False
    (tmp_path / ".env").write_text("ADMIN_API_TOKEN=x\n", encoding="utf-8")
    assert dotenv_files_contain_admin_token(fake_script) is True
