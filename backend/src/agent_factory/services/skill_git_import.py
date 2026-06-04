"""Import Skill package from git URL (docs/04, prd §8.5)."""

from __future__ import annotations

import io
import logging
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from agent_factory.middleware.error_handler import AgentFactoryException

logger = logging.getLogger(__name__)

_GIT_URL_RE = re.compile(
    r"^(https?://|git@)[^\s]+$|^[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+:[^\s]+\.git$"
)


def _validate_git_url(url: str) -> str:
    u = url.strip()
    if not u:
        raise AgentFactoryException(
            "INVALID_PARAMS", "git_url required", status_code=400
        )
    if not _GIT_URL_RE.match(u):
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "git_url must be https/http or git@host:repo.git",
            status_code=400,
        )
    if ".." in u or "\n" in u:
        raise AgentFactoryException(
            "INVALID_PARAMS", "invalid git_url", status_code=400
        )
    return u


def fetch_skill_directory_from_git(git_url: str, *, ref: str = "HEAD") -> Path:
    """Shallow clone into a temp directory; caller must remove parent."""
    url = _validate_git_url(git_url)
    tmp = tempfile.mkdtemp(prefix="skill_git_")
    dest = Path(tmp)
    cmd = [
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        ref if ref != "HEAD" else "main",
        url,
        str(dest / "repo"),
    ]
    if ref == "HEAD":
        cmd = ["git", "clone", "--depth", "1", url, str(dest / "repo")]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise AgentFactoryException(
            "GIT_UNAVAILABLE",
            "git executable not found on server",
            status_code=503,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise AgentFactoryException(
            "GIT_TIMEOUT",
            "git clone timed out",
            status_code=504,
        ) from exc
    if proc.returncode != 0:
        if ref == "HEAD" and "main" in (proc.stderr or ""):
            cmd_fallback = ["git", "clone", "--depth", "1", url, str(dest / "repo")]
            proc = subprocess.run(
                cmd_fallback,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        if proc.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            raise AgentFactoryException(
                "GIT_CLONE_FAILED",
                (proc.stderr or proc.stdout or "clone failed")[:500],
                status_code=400,
            )
    repo = dest / "repo"
    if not repo.is_dir():
        shutil.rmtree(tmp, ignore_errors=True)
        raise AgentFactoryException(
            "GIT_CLONE_FAILED",
            "clone produced no directory",
            status_code=400,
        )
    return repo


def directory_to_tar_gz_bytes(root: Path) -> bytes:
    """Pack directory as ``.tar.gz`` for ``process_skill_tar_gz``."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel.startswith(".git/"):
                continue
            data = path.read_bytes()
            info = tarfile.TarInfo(name=rel)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()
