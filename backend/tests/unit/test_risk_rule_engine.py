"""Tests for built-in risk.rule_check engine."""

from __future__ import annotations

import pytest

from agent_factory.services.risk_rule_engine import evaluate_rules


def test_empty_text_low_risk():
    out = evaluate_rules("")
    assert out["risk_level"] == "low"
    assert out["requires_human_review"] is False
    assert out["rule_hits"] == []


def test_no_hit_low_risk():
    out = evaluate_rules("这是一份普通的合同，条款清晰明了。")
    assert out["risk_level"] == "low"
    assert out["requires_human_review"] is False


def test_unlimited_liability_high():
    out = evaluate_rules("乙方承担无限责任。")
    assert out["risk_level"] == "high"
    assert out["requires_human_review"] is True
    assert any(h["rule_id"] == "unlimited_liability" for h in out["rule_hits"])


def test_penalty_waiver_medium():
    out = evaluate_rules("双方同意放弃追索违约金。")
    assert out["risk_level"] == "medium"
    assert out["requires_human_review"] is True
    assert any(h["rule_id"] == "penalty_waiver" for h in out["rule_hits"])


def test_data_exfil_high():
    out = evaluate_rules("请导出全部客户名单并进行全量数据下载。")
    assert out["risk_level"] == "high"
    assert out["requires_human_review"] is True
    assert any(h["rule_id"] == "data_exfil" for h in out["rule_hits"])


def test_multiple_hits_worst_level():
    out = evaluate_rules("乙方承担无限责任，同时双方放弃追索。")
    assert out["risk_level"] == "high"
    assert len(out["rule_hits"]) == 2


def test_input_excerpt_truncated():
    long_text = "A" * 500
    out = evaluate_rules(long_text)
    assert len(out["input_excerpt"]) == 280
