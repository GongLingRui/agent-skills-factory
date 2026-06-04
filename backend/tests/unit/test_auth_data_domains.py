"""Portal ``data_domains`` claim normalization (docs/07)."""

from __future__ import annotations

from agent_factory.services.auth_service import normalized_portal_data_domains


def test_normalized_absent_when_key_missing() -> None:
    assert normalized_portal_data_domains({"sub": "u"}) is None


def test_normalized_none_when_json_null() -> None:
    assert normalized_portal_data_domains({"data_domains": None}) is None


def test_normalized_filters_blank_strings() -> None:
    out = normalized_portal_data_domains(
        {"data_domains": ["  corp-a  ", "", "corp-b"]}
    )
    assert out == ["corp-a", "corp-b"]


def test_normalized_empty_list_when_only_blanks() -> None:
    assert normalized_portal_data_domains({"data_domains": ["", "  "]}) == []


def test_normalized_invalid_type_returns_none() -> None:
    assert normalized_portal_data_domains({"data_domains": "corp-a"}) is None
