"""Built-in risk.rule_check engine (prd §6; replaces stub-only path)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    pattern: re.Pattern[str]
    risk_level: str
    summary: str


_DEFAULT_RULES: tuple[_Rule, ...] = (
    _Rule(
        "unlimited_liability",
        re.compile(r"无限责任|unlimited\s+liability", re.I),
        "high",
        "检测到无限责任或等价表述",
    ),
    _Rule(
        "penalty_waiver",
        re.compile(r"放弃\s*追索|免除\s*违约|waiver\s+of\s+penalt", re.I),
        "medium",
        "检测到放弃追索/违约金豁免类表述",
    ),
    _Rule(
        "data_exfil",
        re.compile(r"导出\s*全部\s*客户|全量\s*数据\s*下载", re.I),
        "high",
        "检测到大规模数据导出意图相关措辞",
    ),
)


def evaluate_rules(text: str) -> dict[str, Any]:
    """Return structured risk assessment for ``risk.rule_check`` tool."""
    t = (text or "").strip()
    if not t:
        return {
            "risk_level": "low",
            "summary": "空文本",
            "rule_hits": [],
            "requires_human_review": False,
            "input_excerpt": "",
        }
    hits: list[dict[str, str]] = []
    worst = "low"
    order = {"low": 0, "medium": 1, "high": 2}

    for rule in _DEFAULT_RULES:
        if rule.pattern.search(t):
            hits.append(
                {
                    "rule_id": rule.rule_id,
                    "risk_level": rule.risk_level,
                    "summary": rule.summary,
                }
            )
            if order[rule.risk_level] > order[worst]:
                worst = rule.risk_level

    return {
        "risk_level": worst,
        "summary": (
            f"规则引擎命中 {len(hits)} 条"
            if hits
            else "未命中内置规则（仍建议结合业务复核）"
        ),
        "rule_hits": hits,
        "requires_human_review": worst != "low",
        "input_excerpt": t[:280],
    }
