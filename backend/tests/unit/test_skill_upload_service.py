"""Tests for skill tar.gz upload parsing and static analysis."""

from __future__ import annotations

import io
import tarfile

import pytest

from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.skill_upload_service import process_skill_tar_gz


def _make_tar_gz(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_process_skill_tar_gz_ok():
    raw = _make_tar_gz({
        "SKILL.md": b"---\nname: Test Skill\n---\n# Body\n",
        "references/ref.md": b"reference content",
    })
    payload = process_skill_tar_gz(raw, skill_id="test-skill", version="1.0.0")
    assert payload["id"] == "test-skill"
    assert payload["version"] == "1.0.0"
    assert payload["name"] == "Test Skill"
    meta = payload["package_metadata"]
    assert "reference_files" in meta
    assert meta["reference_files"]["references/ref.md"] == "reference content"
    assert "file_manifest" in meta


def test_missing_skill_md():
    raw = _make_tar_gz({"other.txt": b"no skill md"})
    with pytest.raises(AgentFactoryException) as exc:
        process_skill_tar_gz(raw, skill_id="x", version="1")
    assert exc.value.code == "INVALID_PARAMS"


def test_invalid_gzip():
    with pytest.raises(AgentFactoryException) as exc:
        process_skill_tar_gz(b"not a gzip", skill_id="x", version="1")
    assert exc.value.code == "INVALID_FILE_TYPE"


def test_forbidden_import_blocked():
    raw = _make_tar_gz({
        "SKILL.md": b"---\nname: Bad\n---\n",
        "scripts/evil.py": b"import socket\n",
    })
    with pytest.raises(AgentFactoryException) as exc:
        process_skill_tar_gz(raw, skill_id="x", version="1")
    assert exc.value.code == "SKILL_UPLOAD_FORBIDDEN_IMPORT"


def test_forbidden_import_from_blocked():
    raw = _make_tar_gz({
        "SKILL.md": b"---\nname: Bad\n---\n",
        "scripts/evil.py": b"from subprocess import call\n",
    })
    with pytest.raises(AgentFactoryException) as exc:
        process_skill_tar_gz(raw, skill_id="x", version="1")
    assert exc.value.code == "SKILL_UPLOAD_FORBIDDEN_IMPORT"


def test_too_large_rejected():
    big = b"\x1f\x8b" + b"\x00" * (51 * 1024 * 1024)
    with pytest.raises(AgentFactoryException) as exc:
        process_skill_tar_gz(big, skill_id="x", version="1")
    assert exc.value.code == "FILE_TOO_LARGE"


def test_schema_files_extracted():
    schema = b'{"type":"object","properties":{"x":{"type":"string"}}}'
    raw = _make_tar_gz({
        "SKILL.md": b"---\nname: Schema Skill\n---\n",
        "schemas/out.json": schema,
    })
    payload = process_skill_tar_gz(raw, skill_id="schema-skill", version="1.0.0")
    meta = payload["package_metadata"]
    assert "schema_files" in meta
    assert "out" in meta["schema_files"]


def test_syntax_error_in_script():
    raw = _make_tar_gz({
        "SKILL.md": b"---\nname: Bad\n---\n",
        "scripts/broken.py": b"def foo(\n",
    })
    with pytest.raises(AgentFactoryException) as exc:
        process_skill_tar_gz(raw, skill_id="x", version="1")
    assert exc.value.code == "SKILL_UPLOAD_INVALID_SCRIPT"
