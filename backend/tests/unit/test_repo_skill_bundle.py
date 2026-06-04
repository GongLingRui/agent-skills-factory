"""Tests for ``repo_skill_bundle`` (Skill 包目录 → Registry metadata)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_factory.services.repo_skill_bundle import (
    collect_repo_skill_files,
    load_skill_bundle_from_directory,
    parse_skill_md,
    tools_from_skill_frontmatter,
)


def test_parse_skill_md_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "SKILL.md"
    p.write_text(
        "---\nname: demo-skill\n"
        "description: Short desc\n"
        "when_to_use: When testing\n---\n\n# Body\n\nHello.\n",
        encoding="utf-8",
    )
    fm, body = parse_skill_md(p.read_text(encoding="utf-8"))
    assert fm["name"] == "demo-skill"
    assert "Hello" in body


def test_tools_from_frontmatter_defaults_empty() -> None:
    assert tools_from_skill_frontmatter({}) == {
        "require": [],
        "optional": [],
    }


def test_tools_from_frontmatter_parsed() -> None:
    fm = {"tools": {"require": ["doc.extract"], "optional": ["kb.search"]}}
    assert tools_from_skill_frontmatter(fm) == {
        "require": ["doc.extract"],
        "optional": ["kb.search"],
    }


def test_load_skill_bundle_respects_tools_frontmatter(tmp_path: Path) -> None:
    root = tmp_path / "skill"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\n"
        "name: tmp-skill\n"
        "tools:\n"
        "  require: [doc.extract]\n"
        "  optional: [kb.search]\n"
        "---\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    bundle = load_skill_bundle_from_directory(root, version="0.2.0")
    assert bundle["package_metadata"]["tools"] == {
        "require": ["doc.extract"],
        "optional": ["kb.search"],
    }


def test_collect_repo_skill_files_skips_skill_md(tmp_path: Path) -> None:
    root = tmp_path / "s"
    root.mkdir()
    (root / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    sub = root / "references"
    sub.mkdir()
    (sub / "note.md").write_text("# Ref", encoding="utf-8")
    refs, lazy, man = collect_repo_skill_files(root)
    assert "references/note.md" in refs
    assert lazy == [{"name": "note", "path": "references/note.md"}]
    assert len(man) == 1


def test_load_skill_bundle_from_directory_repo_skills() -> None:
    root = Path(__file__).resolve().parents[3]
    bp = root / "agents" / "business-presentation-generator-agent" / "skill"
    if not (bp / "SKILL.md").is_file():
        pytest.skip("agents/business-presentation-generator-agent/skill missing")
    bundle = load_skill_bundle_from_directory(
        bp,
        version="0.1.0",
        storage_path="agents/business-presentation-generator-agent/skill",
    )
    assert bundle["id"] == "business-presentation-generator"
    assert bundle["storage_path"] == "agents/business-presentation-generator-agent/skill"
    meta = bundle["package_metadata"]
    assert "skill_instruction" in meta
    assert "reference_files" in meta
    assert meta["eval_cases"]
    assert meta.get("tools") == {"require": [], "optional": []}
    assert any(
        r["path"].startswith("references/")
        for r in meta["lazy_refs"]
    )
