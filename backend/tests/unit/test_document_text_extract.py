"""Unit tests for ``document_text_extract`` (docs/24)."""

import io
import zipfile

from agent_factory.core.document_text_extract import (
    DOCX_MT,
    PPTX_MT,
    XLSX_MT,
    extract_plain_text,
)


def _minimal_docx(inner: str = "HelloDOCX") -> bytes:
    doc_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{inner}</w:t></w:r></w:p></w:body>
</w:document>""".encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", doc_xml)
    return buf.getvalue()


def test_text_utf8_and_bom():
    raw = "\ufeffplain line".encode("utf-8")
    out = extract_plain_text(raw, "text/plain")
    assert out == "plain line"


def test_docx_extracts_body():
    data = _minimal_docx()
    out = extract_plain_text(data, DOCX_MT)
    assert "HelloDOCX" in out


def test_docx_by_filename_when_mime_octet():
    data = _minimal_docx("ByName")
    out = extract_plain_text(
        data,
        "application/octet-stream",
        file_name="memo.docx",
    )
    assert "ByName" in out


def _minimal_xlsx(
    *,
    shared_text: str = "HelloXLSX",
    inline: bool = False,
) -> bytes:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    if inline:
        cell = (
            f'<c r="A1" t="inlineStr">'
            f"<is><t>{shared_text}</t></is></c>"
        )
        parts: list[tuple[str, str]] = [
            (
                "xl/worksheets/sheet1.xml",
                f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="{ns}">
  <sheetData><row r="1">{cell}</row></sheetData>
</worksheet>""",
            ),
        ]
    else:
        parts = [
            (
                "xl/sharedStrings.xml",
                f"""<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="{ns}" count="1" uniqueCount="1">
  <si><t>{shared_text}</t></si>
</sst>""",
            ),
            (
                "xl/worksheets/sheet1.xml",
                f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="{ns}">
  <sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData>
</worksheet>""",
            ),
        ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, xml in parts:
            zf.writestr(name, xml.encode("utf-8"))
    return buf.getvalue()


def test_xlsx_extracts_shared_string_cell():
    data = _minimal_xlsx()
    out = extract_plain_text(data, XLSX_MT, file_name="book.xlsx")
    assert "HelloXLSX" in out
    assert "sheet1.xml" in out


def test_xlsx_inline_string_cell():
    data = _minimal_xlsx(shared_text="InlineOK", inline=True)
    out = extract_plain_text(data, XLSX_MT)
    assert "InlineOK" in out


def test_xlsx_invalid_zip_returns_empty():
    out = extract_plain_text(b"PK\x03\x04", XLSX_MT, file_name="t.xlsx")
    assert out == ""


def test_pdf_invalid_returns_empty_string():
    out = extract_plain_text(b"not pdf content", "application/pdf")
    assert out == ""


def test_pptx_collects_slide_text():
    slide = b"""<?xml version="1.0"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <a:t>SlideHello</a:t>
  </p:spTree></p:cSld>
</p:sld>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ppt/slides/slide1.xml", slide)
    out = extract_plain_text(buf.getvalue(), PPTX_MT)
    assert "SlideHello" in out
