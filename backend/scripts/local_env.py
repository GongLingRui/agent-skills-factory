"""Load ``.env`` for CLI sync scripts (align with ``settings.py`` file order).

- Reads **repository root** ``.env`` then ``backend/.env`` (same order as
  :mod:`agent_factory.config.settings`; later file wins on duplicate keys).
- Only sets a key when the current process value is **missing or blank**,
  so an empty ``export ADMIN_API_TOKEN=`` does not block values from files.
"""

from __future__ import annotations

import os
from pathlib import Path


def repo_and_backend_dotenv_paths(script_file: Path) -> tuple[Path, Path]:
    """``script_file`` is e.g. ``.../backend/scripts/sync_*.py``."""
    backend_dir = script_file.resolve().parent.parent
    repo_root = backend_dir.parent
    return repo_root / ".env", backend_dir / ".env"


def _parse_dotenv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        out[key] = val
    return out


def load_env_for_sync_scripts(script_file: Path) -> tuple[Path | None, Path | None]:
    """Merge dotenv files into ``os.environ``; return paths that exist."""
    root_env, backend_env = repo_and_backend_dotenv_paths(script_file)
    merged: dict[str, str] = {}
    merged.update(_parse_dotenv_file(root_env))
    merged.update(_parse_dotenv_file(backend_env))
    # Drop empty assignments so a blank line in backend/.env does not win.
    merged = {k: v for k, v in merged.items() if v.strip()}

    for key, val in merged.items():
        cur = os.environ.get(key)
        if cur is not None and str(cur).strip() != "":
            continue
        os.environ[key] = val

    return (
        root_env if root_env.is_file() else None,
        backend_env if backend_env.is_file() else None,
    )


def dotenv_files_contain_admin_token(script_file: Path) -> bool:
    """True if any loaded dotenv layer has a non-empty ``ADMIN_API_TOKEN``."""
    root_env, backend_env = repo_and_backend_dotenv_paths(script_file)
    merged: dict[str, str] = {}
    merged.update(_parse_dotenv_file(root_env))
    merged.update(_parse_dotenv_file(backend_env))
    v = merged.get("ADMIN_API_TOKEN")
    return isinstance(v, str) and bool(v.strip())
