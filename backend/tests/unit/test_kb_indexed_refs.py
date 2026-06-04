"""Tests for kb indexed reference catalog."""

from __future__ import annotations

from agent_factory.services.kb_indexed_refs import (
    build_indexed_catalog,
    normalize_kb_results,
)


def test_build_indexed_catalog_strings():
    out = build_indexed_catalog(["legal-policy", "contracts"])
    assert out[0]["name"] == "legal-policy"
    assert out[0]["scope"] == "legal-policy"


def test_build_indexed_catalog_dicts():
    out = build_indexed_catalog(
        [{"name": "a", "scope": "group_a"}],
    )
    assert out == [{"name": "a", "scope": "group_a"}]


def test_normalize_kb_results_maps_fields():
    data = {
        "results": [{"doc_id": "x", "content": "snippet text"}],
    }
    norm = normalize_kb_results(data)
    assert norm["results"][0]["id"] == "x"
    assert norm["results"][0]["snippet"] == "snippet text"
    assert norm["total"] == 1
