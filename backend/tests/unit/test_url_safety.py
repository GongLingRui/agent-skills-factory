"""Tests for outbound URL validation (信息安全 / SSRF mitigation)."""

import pytest

from agent_factory.core.url_safety import validate_outbound_http_url


def test_https_public_hostname_ok():
    validate_outbound_http_url(
        "https://kb.example.com/v1/search",
        allow_http=False,
        allow_private_hosts=False,
    )


def test_http_rejected_without_allow_http():
    with pytest.raises(ValueError, match="http URL not allowed"):
        validate_outbound_http_url(
            "http://kb.example.com/search",
            allow_http=False,
            allow_private_hosts=False,
        )


def test_http_ok_when_explicitly_allowed():
    validate_outbound_http_url(
        "http://kb.example.com/search",
        allow_http=True,
        allow_private_hosts=False,
    )


@pytest.mark.parametrize(
    "url",
    (
        "https://127.0.0.1/x",
        "https://10.0.0.1/x",
        "https://192.168.1.1/x",
        "https://172.16.0.1/x",
        "https://[::1]/x",
    ),
)
def test_literal_private_or_loopback_blocked(url: str):
    with pytest.raises(ValueError, match="literal IP"):
        validate_outbound_http_url(
            url,
            allow_http=True,
            allow_private_hosts=False,
        )


def test_private_ip_allowed_for_lab_flag():
    validate_outbound_http_url(
        "https://10.0.0.1/x",
        allow_http=True,
        allow_private_hosts=True,
    )


@pytest.mark.parametrize(
    "url",
    (
        "https://localhost/x",
        "https://metadata.google.internal/",
    ),
)
def test_blocked_hostnames(url: str):
    with pytest.raises(ValueError, match="not allowed"):
        validate_outbound_http_url(
            url,
            allow_http=True,
            allow_private_hosts=False,
        )


def test_userinfo_rejected():
    with pytest.raises(ValueError, match="userinfo"):
        validate_outbound_http_url(
            "https://user:pass@example.com/x",
            allow_http=False,
            allow_private_hosts=False,
        )


def test_non_http_scheme_rejected():
    with pytest.raises(ValueError, match="Only http"):
        validate_outbound_http_url(
            "ftp://example.com/x",
            allow_http=True,
            allow_private_hosts=False,
        )
