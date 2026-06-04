"""Resolve Skill on-demand references for ``read_reference`` (docs/09, 04)."""

from __future__ import annotations

import hashlib
import logging
from pathlib import PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)

_TEXT_SUFFIXES = (".md", ".txt", ".yaml", ".yml", ".json", ".html", ".htm")


def _lazy_path_candidates(name: str) -> list[str]:
    """Prefer ``references/`` then ``reference/`` (prd.md §6.4)."""
    n = name.strip()
    if n.endswith(".md"):
        return [f"references/{n}", f"reference/{n}"]
    return [
        f"references/{n}.md",
        f"reference/{n}.md",
        f"references/{n}",
        f"reference/{n}",
    ]


def _pick_path_for_string_lazy(
    name: str,
    reference_file_keys: frozenset[str] | None,
) -> str:
    if reference_file_keys:
        for p in _lazy_path_candidates(name):
            if p in reference_file_keys:
                return p
    return f"references/{name.strip()}.md"


def normalize_reference_lookup_name(name: str) -> str:
    """Strip paths/extensions so ``fsm-state-contracts.md`` matches lazy name."""
    n = name.strip().strip("\"'")
    if not n:
        return ""
    if "/" in n or "\\" in n:
        n = PurePosixPath(n.replace("\\", "/")).name
    lower = n.lower()
    for ext in _TEXT_SUFFIXES:
        if lower.endswith(ext):
            n = n[: -len(ext)]
            break
    return n.strip()


def collect_lazy_reference_names(lazy_refs: Any) -> list[str]:
    """Ordered unique ``read_reference`` names from RunSpec lazy refs."""
    if not lazy_refs or not isinstance(lazy_refs, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in lazy_refs:
        if isinstance(item, str):
            n = normalize_reference_lookup_name(item)
        elif isinstance(item, dict):
            n = normalize_reference_lookup_name(str(item.get("name") or ""))
        else:
            continue
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def find_lazy_reference_entry(
    lazy_refs: Any,
    name: str,
    *,
    reference_file_keys: frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Return the lazy reference dict for ``name``, or ``None``."""
    if not lazy_refs or not isinstance(lazy_refs, list):
        return None
    want = normalize_reference_lookup_name(name)
    if not want:
        return None
    for item in lazy_refs:
        if isinstance(item, str):
            n = normalize_reference_lookup_name(item)
            if n == want:
                path = _pick_path_for_string_lazy(n, reference_file_keys)
                return {"name": n, "path": path}
        if isinstance(item, dict):
            n = normalize_reference_lookup_name(str(item.get("name") or ""))
            if n == want:
                return dict(item)
            path = item.get("path")
            if isinstance(path, str) and path.strip():
                stem = PurePosixPath(path.replace("\\", "/")).stem
                if stem == want:
                    return dict(item)
    return None


def resolve_reference_text(
    entry: dict[str, Any],
    package_metadata: dict[str, Any],
) -> str | None:
    """Resolve UTF-8 text from inline ``content`` or ``reference_files`` map."""
    raw = entry.get("content")
    if isinstance(raw, str) and raw.strip():
        return raw
    ref_files = package_metadata.get("reference_files")
    if not isinstance(ref_files, dict):
        return None
    path = entry.get("path")
    if isinstance(path, str) and path in ref_files:
        val = ref_files[path]
        return val if isinstance(val, str) else None
    if isinstance(path, str) and path.startswith("references/"):
        alt = "reference/" + path[len("references/"):]
        if alt in ref_files:
            val = ref_files[alt]
            return val if isinstance(val, str) else None
    if isinstance(path, str) and path.startswith("reference/"):
        alt = "references/" + path[len("reference/"):]
        if alt in ref_files:
            val = ref_files[alt]
            return val if isinstance(val, str) else None
    ref_name = entry.get("name")
    if isinstance(ref_name, str) and ref_name in ref_files:
        val = ref_files[ref_name]
        return val if isinstance(val, str) else None
    return None


def verify_reference_manifest_hash(
    manifest: Any,
    path: str,
    text: str,
) -> None:
    """Raise ``ValueError`` if manifest records a hash that does not match."""
    if not manifest or not isinstance(manifest, dict):
        return
    expected = manifest.get(path)
    if expected is None:
        return
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if isinstance(expected, str):
        if expected == digest:
            return
        logger.warning("reference hash mismatch path=%s", path)
        raise ValueError("REFERENCE_HASH_MISMATCH")
    if isinstance(expected, dict):
        h = expected.get("sha256")
        if isinstance(h, str) and h == digest:
            return
        logger.warning("reference hash mismatch path=%s", path)
        raise ValueError("REFERENCE_HASH_MISMATCH")
