"""Unit tests for patch_agent_tags."""

from __future__ import annotations

from agent_factory.services.agent_registry_service import _normalize_tags


def test_normalize_tags_trims_dedupes() -> None:
    assert _normalize_tags([" 产品 ", "产品", "", "设计", " 设计"]) == [
        "产品",
        "设计",
    ]


def test_normalize_tags_empty() -> None:
    assert _normalize_tags(None) == []
    assert _normalize_tags([]) == []
