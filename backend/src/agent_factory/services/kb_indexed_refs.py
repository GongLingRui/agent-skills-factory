"""Map RunSpec ``indexed_references`` to kb.search upstream payload (docs/05)."""

from __future__ import annotations

from typing import Any


def build_indexed_catalog(indexed_references: list[Any] | None) -> list[dict[str, str]]:
    """Normalize indexed refs for external KB (name + scope)."""
    if not indexed_references:
        return []
    out: list[dict[str, str]] = []
    for item in indexed_references:
        if isinstance(item, str):
            name = item.strip()
            if name:
                out.append({"name": name, "scope": name})
            continue
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        scope = str(item.get("scope") or name).strip()
        if name or scope:
            out.append({"name": name or scope, "scope": scope or name})
    return out


def normalize_kb_results(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure ``results`` list items have id/title/snippet keys."""
    results = data.get("results")
    if not isinstance(results, list):
        return {**data, "results": [], "total": 0}
    norm: list[dict[str, Any]] = []
    for i, row in enumerate(results):
        if not isinstance(row, dict):
            continue
        rid = row.get("id") or row.get("doc_id") or f"hit_{i}"
        title = row.get("title") or row.get("name") or ""
        snippet = (
            row.get("snippet")
            or row.get("text")
            or row.get("content")
            or ""
        )
        norm.append(
            {
                **row,
                "id": str(rid),
                "title": str(title),
                "snippet": str(snippet)[:4000],
            }
        )
    total = data.get("total")
    if not isinstance(total, int):
        total = len(norm)
    return {**data, "results": norm, "total": total}
