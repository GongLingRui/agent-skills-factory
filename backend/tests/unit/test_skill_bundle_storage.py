"""Tests for skill bundle tar storage helpers."""

from __future__ import annotations

import io
import tarfile

from agent_factory.services.skill_bundle_storage import (
    compute_tarball_sha256,
    extract_text_from_tarball,
    skill_bundle_object_key,
)


def _tar_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_skill_bundle_object_key():
    assert skill_bundle_object_key("a/b", "1.0") == "skills/a_b/1.0/package.tar.gz"


def test_extract_reference_from_tarball():
    raw = _tar_bytes({
        "SKILL.md": "---\nname: T\n---\n",
        "references/checklist.md": "checklist body",
    })
    text = extract_text_from_tarball(raw, "references/checklist.md")
    assert text == "checklist body"


def test_compute_tarball_sha256_stable():
    raw = _tar_bytes({"SKILL.md": "x"})
    h1 = compute_tarball_sha256(raw)
    h2 = compute_tarball_sha256(raw)
    assert h1 == h2
