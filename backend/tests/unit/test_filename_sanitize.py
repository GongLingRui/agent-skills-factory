"""Tests for upload filename sanitization."""

from agent_factory.core.filename_sanitize import sanitize_upload_filename


def test_empty_becomes_upload():
    assert sanitize_upload_filename("") == "upload"
    assert sanitize_upload_filename(None) == "upload"


def test_basename_only():
    assert sanitize_upload_filename("a/b/../secret.txt") == "secret.txt"


def test_null_byte_truncates():
    out = sanitize_upload_filename("good\x00/../../evil.exe")
    assert "\x00" not in out
    assert "evil" not in out.lower()
    assert out.startswith("good")
    assert sanitize_upload_filename("ok\x00nul") == "ok"


def test_reserved_windows_name_prefixed():
    out = sanitize_upload_filename("CON.pdf")
    assert out.startswith("_")


def test_max_len_truncates():
    long = "a" * 300 + ".pdf"
    out = sanitize_upload_filename(long, max_len=50)
    assert len(out) <= 50
    assert out.endswith(".pdf")
