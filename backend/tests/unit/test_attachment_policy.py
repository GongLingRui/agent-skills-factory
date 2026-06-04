"""Tests for ui_config.attachments upload validation."""

from agent_factory.core.attachment_policy import (
    sniff_mime_magic,
    validate_upload_for_ui_config,
)

_PDF_HEAD = b"%PDF-1.4\n"
_PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
_MZ_HEAD = b"MZ\x90\x00" + b"\x00" * 64


def test_default_accepts_when_no_attachments_section():
    ok, err = validate_upload_for_ui_config(
        filename="a.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        ui_config={},
    )
    assert ok is True
    assert err is None


def test_disabled():
    ok, err = validate_upload_for_ui_config(
        filename="a.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        ui_config={"attachments": {"enabled": False}},
    )
    assert ok is False
    assert err == "ATTACHMENTS_DISABLED"


def test_max_size_mb():
    ok, err = validate_upload_for_ui_config(
        filename="a.bin",
        mime_type="application/octet-stream",
        size_bytes=2 * 1024 * 1024,
        ui_config={"attachments": {"max_size_mb": 1}},
    )
    assert ok is False
    assert err == "FILE_TOO_LARGE"


def test_accept_extension():
    ok, err = validate_upload_for_ui_config(
        filename="x.PDF",
        mime_type="application/octet-stream",
        size_bytes=10,
        ui_config={"attachments": {"accept": [".pdf"]}},
    )
    assert ok is True


def test_accept_extension_rejects():
    ok, err = validate_upload_for_ui_config(
        filename="x.exe",
        mime_type="application/octet-stream",
        size_bytes=10,
        ui_config={"attachments": {"accept": [".pdf"]}},
    )
    assert ok is False
    assert err == "FILE_TYPE_NOT_ALLOWED"


def test_accept_mime_glob():
    ok, err = validate_upload_for_ui_config(
        filename="p.png",
        mime_type="image/png",
        size_bytes=10,
        ui_config={"attachments": {"accept": ["image/*"]}},
    )
    assert ok is True


def test_accept_exact_mime():
    ok, err = validate_upload_for_ui_config(
        filename="t.txt",
        mime_type="text/plain",
        size_bytes=10,
        ui_config={"attachments": {"accept": ["text/plain"]}},
    )
    assert ok is True


def test_sniff_mime_magic_pdf_png():
    assert sniff_mime_magic(_PDF_HEAD) == "application/pdf"
    assert sniff_mime_magic(_PNG_HEAD) == "image/png"
    assert sniff_mime_magic(_MZ_HEAD) == "application/x-msdownload"
    assert sniff_mime_magic(b"") is None


def test_octet_stream_refined_by_magic_for_accept():
    ok, err = validate_upload_for_ui_config(
        filename="a.pdf",
        mime_type="application/octet-stream",
        size_bytes=len(_PDF_HEAD),
        ui_config={"attachments": {"accept": ["application/pdf"]}},
        content_head=_PDF_HEAD,
    )
    assert ok is True
    assert err is None


def test_pdf_extension_with_png_magic_rejected():
    ok, err = validate_upload_for_ui_config(
        filename="disguise.pdf",
        mime_type="application/pdf",
        size_bytes=len(_PNG_HEAD),
        ui_config=None,
        content_head=_PNG_HEAD,
    )
    assert ok is False
    assert err == "MIME_MAGIC_MISMATCH"


def test_pe_disguised_as_pdf_rejected():
    ok, err = validate_upload_for_ui_config(
        filename="trojan.pdf",
        mime_type="application/octet-stream",
        size_bytes=len(_MZ_HEAD),
        ui_config=None,
        content_head=_MZ_HEAD,
    )
    assert ok is False
    assert err == "MIME_MAGIC_MISMATCH"


def test_declared_mime_conflicts_with_magic():
    ok, err = validate_upload_for_ui_config(
        filename="x.bin",
        mime_type="image/jpeg",
        size_bytes=len(_PNG_HEAD),
        ui_config=None,
        content_head=_PNG_HEAD,
    )
    assert ok is False
    assert err == "MIME_MAGIC_MISMATCH"


def test_docx_zip_magic_compatible():
    """OOXML is ZIP; declared docx mime matches sniffed zip family."""
    zip_head = b"PK\x03\x04" + b"\x00" * 64
    ok, err = validate_upload_for_ui_config(
        filename="w.docx",
        mime_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        size_bytes=500,
        ui_config={"attachments": {"accept": [".docx"]}},
        content_head=zip_head,
    )
    assert ok is True
    assert err is None
