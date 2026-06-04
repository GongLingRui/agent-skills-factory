"""Upload SHA-256 helper (docs/39 file_uploads.sha256)."""

from __future__ import annotations

from agent_factory.api.v1.agents import _body_sha256_hex


def test_body_sha256_hex_empty() -> None:
    assert (
        _body_sha256_hex(b"")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_body_sha256_hex_ascii() -> None:
    assert (
        _body_sha256_hex(b"hello")
        == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )
