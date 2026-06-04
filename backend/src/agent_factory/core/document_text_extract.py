"""Best-effort plain text extraction from upload bytes (docs/24, plan §12).

In-memory only; used by ``document_parser_worker``. PDF uses ``pypdf``;
DOCX/PPTX use stdlib ``zipfile`` + ``xml.etree`` (no python-docx).
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

DOCX_MT = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)
XLSX_MT = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
PPTX_MT = (
    "application/vnd.openxmlformats-officedocument."
    "presentationml.presentation"
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _normalize_mime(mime_type: str, file_name: str) -> str:
    mt = (mime_type or "").strip().lower()
    fn = file_name.lower()
    if mt not in ("", "application/octet-stream", "binary/octet-stream"):
        return mt
    if fn.endswith(".pdf"):
        return "application/pdf"
    if fn.endswith(".docx"):
        return DOCX_MT
    if fn.endswith(".pptx"):
        return PPTX_MT
    if fn.endswith(".xlsx"):
        return XLSX_MT
    if fn.endswith(".md"):
        return "text/markdown"
    if fn.endswith(".csv"):
        return "text/csv"
    return mt or "application/octet-stream"


def _decode_text_bytes(contents: bytes) -> str:
    if contents.startswith(b"\xef\xbb\xbf"):
        contents = contents[3:]
    for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            return contents.decode(enc)
        except UnicodeDecodeError:
            continue
    return contents.decode("utf-8", errors="replace")


def _extract_docx(contents: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            if "word/document.xml" not in zf.namelist():
                return ""
            raw = zf.read("word/document.xml")
    except (zipfile.BadZipFile, OSError, KeyError) as exc:
        logger.debug("docx zip parse skip: %s", exc)
        return ""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return ""
    tag_t = f"{{{W_NS}}}t"
    parts: list[str] = []
    for el in root.iter():
        if el.tag == tag_t and el.text:
            parts.append(el.text)
    return "".join(parts)


def _parse_xlsx_shared_strings(raw: bytes) -> list[str]:
    """Build shared string table from ``xl/sharedStrings.xml``."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    out: list[str] = []
    for si in root:
        if not (si.tag == "si" or si.tag.endswith("}si")):
            continue
        parts: list[str] = []
        for el in si.iter():
            if el.tag.endswith("}t") and el.text:
                parts.append(el.text)
        out.append("".join(parts))
    return out


def _xlsx_worksheet_paths(namelist: list[str]) -> list[str]:
    paths = [
        n
        for n in namelist
        if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
    ]

    def sort_key(path: str) -> tuple[int, str]:
        base = path.rsplit("/", maxsplit=1)[-1]
        m = re.match(r"sheet(\d+)\.xml$", base, flags=re.IGNORECASE)
        if m:
            return int(m.group(1)), path
        return 9999, path

    return sorted(paths, key=sort_key)


def _xlsx_sheet_lines(raw: bytes, shared: list[str]) -> list[str]:
    """Turn one worksheet XML into tab-separated row lines."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    sheet_data = None
    for el in root.iter():
        if el.tag.endswith("}sheetData"):
            sheet_data = el
            break
    if sheet_data is None:
        return []
    lines: list[str] = []
    for row in sheet_data:
        if not row.tag.endswith("}row"):
            continue
        cells: list[str] = []
        for c in row:
            if not c.tag.endswith("}c"):
                continue
            ctype = c.get("t")
            v_el = None
            is_el = None
            for child in c:
                if child.tag.endswith("}v"):
                    v_el = child
                elif child.tag.endswith("}is"):
                    is_el = child
            val = ""
            if ctype == "inlineStr" and is_el is not None:
                for t_el in is_el.iter():
                    if t_el.tag.endswith("}t") and t_el.text:
                        val += t_el.text
            elif v_el is not None and v_el.text is not None:
                raw_v = v_el.text
                if ctype == "s":
                    try:
                        idx = int(raw_v)
                    except ValueError:
                        idx = -1
                    if 0 <= idx < len(shared):
                        val = shared[idx]
                else:
                    val = raw_v
            if val:
                cells.append(val)
        if cells:
            lines.append("\t".join(cells))
    return lines


def _extract_xlsx(contents: bytes) -> str:
    """Best-effort tabular text via OOXML zip + XML (no openpyxl)."""
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            names = zf.namelist()
            shared: list[str] = []
            ss_path = "xl/sharedStrings.xml"
            if ss_path in names:
                shared = _parse_xlsx_shared_strings(zf.read(ss_path))
            chunks: list[str] = []
            for path in _xlsx_worksheet_paths(names):
                try:
                    raw = zf.read(path)
                except KeyError:
                    continue
                lines = _xlsx_sheet_lines(raw, shared)
                if lines:
                    sheet_label = path.rsplit("/", maxsplit=1)[-1]
                    chunks.append(f"--- {sheet_label} ---\n")
                    chunks.append("\n".join(lines))
            return "\n".join(chunks).strip()
    except (zipfile.BadZipFile, OSError) as exc:
        logger.debug("xlsx zip parse skip: %s", exc)
        return ""


def _extract_pptx(contents: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            names = sorted(
                n for n in zf.namelist() if n.startswith("ppt/slides/slide")
                and n.endswith(".xml")
            )
            chunks: list[str] = []
            for name in names:
                try:
                    root = ET.fromstring(zf.read(name))
                except ET.ParseError:
                    continue
                for el in root.iter():
                    if el.tag.endswith("}t") and el.text:
                        chunks.append(el.text)
                chunks.append("\n")
            return "".join(chunks)
    except (zipfile.BadZipFile, OSError, KeyError) as exc:
        logger.debug("pptx zip parse skip: %s", exc)
        return ""


def _extract_pdf(contents: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "(PDF extraction unavailable: pypdf not installed)"
    try:
        reader = PdfReader(io.BytesIO(contents))
        pages: list[str] = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
        return "\n".join(pages).strip()
    except Exception as exc:
        logger.info("pdf extract failed: %s", exc)
        return ""


def extract_plain_text(
    contents: bytes,
    mime_type: str,
    *,
    file_name: str = "",
) -> str:
    """Return UTF-8 logical text; empty string if nothing extracted."""
    mt = _normalize_mime(mime_type, file_name)
    if mt.startswith("text/") or mt in ("text/markdown", "text/csv"):
        return _decode_text_bytes(contents)
    if mt == "application/pdf":
        return _extract_pdf(contents)
    if mt == DOCX_MT:
        return _extract_docx(contents)
    if mt == PPTX_MT:
        return _extract_pptx(contents)
    if mt == XLSX_MT:
        return _extract_xlsx(contents)
    return "(unsupported or unknown document type for text extraction)"
