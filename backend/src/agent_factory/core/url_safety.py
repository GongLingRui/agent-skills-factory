"""Outbound URL validation (SSRF / 信息安全 §3.2 item 10)."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

# Userinfo in authority enables credential phishing / odd client behavior.
_USERINFO = re.compile(r"^[^@]+@")


def validate_outbound_http_url(
    url: str,
    *,
    allow_http: bool,
    allow_private_hosts: bool,
) -> None:
    """Raise ValueError when ``url`` must not be fetched server-side.

    Blocks obviously dangerous targets (loopback/private/link-local IPs,
    metadata hostnames). Corporate hostnames without DNS resolution are
    allowed; pair with network egress policy in production.

    Args:
        url: Absolute HTTP(S) URL.
        allow_http: When False, only ``https`` is accepted.
        allow_private_hosts: When True, literal private/link-local IPs are
            allowed (lab only; never enable in untrusted multi-tenant prod).
    """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("URL is empty")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are allowed")
    if parsed.scheme == "http" and not allow_http:
        raise ValueError("http URL not allowed; use https")
    if not parsed.hostname:
        raise ValueError("URL must include a host")
    if _USERINFO.match(parsed.netloc or ""):
        raise ValueError("URL must not contain userinfo")

    host = parsed.hostname.strip().lower()

    if host in (
        "localhost",
        "metadata.google.internal",
        "metadata",
    ) or host.endswith(".localhost"):
        raise ValueError("host not allowed")
    if host == "169.254.169.254":
        raise ValueError("host not allowed")

    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return

    if allow_private_hosts:
        return
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    ):
        raise ValueError("literal IP target not allowed")
