"""Tests for ``read_reference`` resolution helpers (docs/09)."""

import hashlib

import pytest

from agent_factory.core.read_reference import (
    collect_lazy_reference_names,
    find_lazy_reference_entry,
    normalize_reference_lookup_name,
    resolve_reference_text,
    verify_reference_manifest_hash,
)


def test_find_lazy_by_dict_name():
    lazy = [{"name": "a", "path": "references/a.md"}]
    assert find_lazy_reference_entry(lazy, "a") == lazy[0]
    assert find_lazy_reference_entry(lazy, "b") is None


def test_find_lazy_accepts_md_suffix_and_path():
    lazy = [{"name": "a", "path": "references/a.md"}]
    assert find_lazy_reference_entry(lazy, "a.md") == lazy[0]
    assert find_lazy_reference_entry(lazy, "references/a.md") == lazy[0]


def test_find_lazy_matches_path_stem_when_name_missing():
    lazy = [{"path": "references/checklist.md"}]
    got = find_lazy_reference_entry(lazy, "checklist.md")
    assert got == {"path": "references/checklist.md"}


def test_normalize_reference_lookup_name():
    assert normalize_reference_lookup_name("references/foo.md") == "foo"
    assert normalize_reference_lookup_name("foo.md") == "foo"
    assert normalize_reference_lookup_name("  foo  ") == "foo"


def test_collect_lazy_reference_names():
    lazy = [
        {"name": "a", "path": "references/a.md"},
        "b",
    ]
    assert collect_lazy_reference_names(lazy) == ["a", "b"]
    lazy = ["checklist"]
    got = find_lazy_reference_entry(lazy, "checklist")
    assert got == {"name": "checklist", "path": "references/checklist.md"}


def test_find_lazy_string_prefers_references_key_order():
    lazy = ["note"]
    keys = frozenset({"reference/note.md", "references/note.md"})
    got = find_lazy_reference_entry(lazy, "note", reference_file_keys=keys)
    assert got == {"name": "note", "path": "references/note.md"}


def test_find_lazy_string_falls_back_to_reference_dir():
    lazy = ["note"]
    keys = frozenset({"reference/note.md"})
    got = find_lazy_reference_entry(lazy, "note", reference_file_keys=keys)
    assert got == {"name": "note", "path": "reference/note.md"}


def test_resolve_inline_content():
    entry = {"name": "x", "content": " body "}
    assert resolve_reference_text(entry, {}) == " body "


def test_resolve_from_reference_files_by_path():
    entry = {"name": "r", "path": "references/r.md"}
    meta = {"reference_files": {"references/r.md": "FILE"}}
    assert resolve_reference_text(entry, meta) == "FILE"


def test_resolve_fallback_from_reference_to_references():
    entry = {"name": "r", "path": "reference/r.md"}
    meta = {"reference_files": {"references/r.md": "ALT"}}
    assert resolve_reference_text(entry, meta) == "ALT"


def test_resolve_fallback_from_references_to_reference():
    entry = {"name": "r", "path": "references/r.md"}
    meta = {"reference_files": {"reference/r.md": "LEG"}}
    assert resolve_reference_text(entry, meta) == "LEG"


def test_resolve_from_reference_files_by_name_key():
    entry = {"name": "r"}
    meta = {"reference_files": {"r": "BYNAME"}}
    assert resolve_reference_text(entry, meta) == "BYNAME"


def test_manifest_hash_ok():
    text = "hi"
    h = hashlib.sha256(text.encode()).hexdigest()
    verify_reference_manifest_hash({"references/x.md": h}, "references/x.md", text)


def test_manifest_hash_mismatch():
    text = "hi"
    with pytest.raises(ValueError, match="REFERENCE_HASH_MISMATCH"):
        verify_reference_manifest_hash(
            {"references/x.md": "deadbeef"},
            "references/x.md",
            text,
        )
