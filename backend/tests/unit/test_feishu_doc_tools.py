"""Unit tests for Feishu doc tool helpers."""

from __future__ import annotations

from agent_factory.services.feishu_doc_tools import (
    build_agents_markdown_for_feishu_doc,
    clean_blocks_for_descendant,
    extract_doc_token,
    normalize_converted_block_tree,
    split_markdown_by_headings,
)


def test_extract_doc_token_from_url():
    url = "https://example.feishu.cn/docx/doxcnABC123"
    assert extract_doc_token(url) == "doxcnABC123"
    assert extract_doc_token("doxcnABC123") == "doxcnABC123"


def test_normalize_converted_block_tree_order():
    blocks = [
        {"block_id": "b2", "block_type": 2, "parent_id": "root"},
        {"block_id": "b1", "block_type": 3, "parent_id": "root"},
    ]
    ordered, roots = normalize_converted_block_tree(blocks, ["b1", "b2"])
    assert roots == ["b1", "b2"]
    assert [b["block_id"] for b in ordered] == ["b1", "b2"]


def test_clean_blocks_for_descendant_strips_merge_info():
    blocks = [
        {
            "block_id": "t1",
            "block_type": 31,
            "parent_id": "root",
            "table": {
                "property": {"row_size": 2, "column_size": 3},
                "merge_info": {"x": 1},
            },
        }
    ]
    cleaned = clean_blocks_for_descendant(blocks)
    assert "parent_id" not in cleaned[0]
    assert "merge_info" not in cleaned[0].get("table", {})
    assert cleaned[0]["table"]["property"]["row_size"] == 2


def test_split_markdown_by_headings():
    md = "# A\n\npara\n\n## B\n\nmore"
    chunks = split_markdown_by_headings(md)
    assert len(chunks) == 2
    assert chunks[0].startswith("# A")
    assert chunks[1].startswith("## B")


def test_build_agents_markdown_for_feishu_doc():
    md = build_agents_markdown_for_feishu_doc(
        [
            {"id": "demo-agent", "name": "Demo", "description": "测试"},
            {"id": "work-summary-agent", "name": "总结", "description": ""},
        ]
    )
    assert "demo-agent" in md
    assert "work-summary-agent" in md
    assert "| ID |" in md
