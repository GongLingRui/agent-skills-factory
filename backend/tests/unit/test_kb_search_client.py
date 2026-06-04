"""Tests for kb.search HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_factory.services.kb_search_client import post_kb_search


class _FakeSettings:
    KB_SEARCH_URL = "https://kb.example.com/search"
    KB_SEARCH_ALLOW_HTTP = False
    KB_SEARCH_ALLOW_PRIVATE_HOSTS = False
    KB_SEARCH_BEARER_TOKEN = "secret"
    KB_SEARCH_TIMEOUT_SECONDS = 5.0


def _fake_settings():
    return _FakeSettings()


@pytest.mark.asyncio
async def test_post_kb_search_success():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json = MagicMock(return_value={"results": [{"id": "1", "text": "hello"}]})

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(return_value=fake_resp)

    with patch("agent_factory.services.kb_search_client.httpx.AsyncClient", return_value=fake_client):
        result = await post_kb_search(
            _fake_settings(),
            params={"query": "test", "scope": "public"},
            retrieval_scopes=["scope1"],
            indexed_references=None,
            degradation_knobs=None,
        )

    assert result is not None
    assert result["results"][0]["id"] == "1"
    call_args = fake_client.post.call_args
    assert call_args[1]["json"]["query"] == "test"
    assert call_args[1]["headers"]["Authorization"] == "Bearer secret"


@pytest.mark.asyncio
async def test_post_kb_search_no_url():
    s = _FakeSettings()
    s.KB_SEARCH_URL = ""
    result = await post_kb_search(
        s,
        params={"query": "test"},
        retrieval_scopes=[],
        indexed_references=None,
        degradation_knobs=None,
    )
    assert result is None


@pytest.mark.asyncio
async def test_post_kb_search_http_error():
    fake_resp = MagicMock()
    fake_resp.status_code = 500
    fake_resp.text = "error"

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(return_value=fake_resp)

    with patch("agent_factory.services.kb_search_client.httpx.AsyncClient", return_value=fake_client):
        result = await post_kb_search(
            _fake_settings(),
            params={"query": "test"},
            retrieval_scopes=[],
            indexed_references=None,
            degradation_knobs=None,
        )
    assert result is None
