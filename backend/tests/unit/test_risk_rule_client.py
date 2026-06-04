"""Tests for risk.rule_check HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_factory.services.risk_rule_client import post_risk_rule_check


class _Settings:
    RISK_RULE_CHECK_URL = "https://risk.example/check"
    RISK_RULE_CHECK_BEARER_TOKEN = "tok"
    RISK_RULE_CHECK_TIMEOUT_SECONDS = 5.0
    RISK_RULE_CHECK_ALLOW_HTTP = False
    RISK_RULE_CHECK_ALLOW_PRIVATE_HOSTS = False


@pytest.mark.asyncio
async def test_post_risk_success():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json = MagicMock(
        return_value={"risk_level": "high", "rule_hits": []},
    )
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(return_value=fake_resp)

    with patch(
        "agent_factory.services.risk_rule_client.httpx.AsyncClient",
        return_value=fake_client,
    ):
        out = await post_risk_rule_check(_Settings(), text="无限责任条款")
    assert out is not None
    assert out["risk_level"] == "high"


@pytest.mark.asyncio
async def test_post_risk_no_url():
    s = _Settings()
    s.RISK_RULE_CHECK_URL = ""
    assert await post_risk_rule_check(s, text="x") is None
