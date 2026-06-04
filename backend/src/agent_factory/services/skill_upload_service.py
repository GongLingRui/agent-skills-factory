"""Skill tar.gz upload: validate, static scan scripts/, build metadata."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import tarfile
from typing import Any

from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.repo_skill_bundle import parse_skill_md


_SCRIPT_BLACKLIST_MODULES = frozenset(
    {"socket", "subprocess", "ctypes", "multiprocessing", "ssl"}
)


def _scan_script_ast(source: str, path: str) -> None:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        raise AgentFactoryException(
            "SKILL_UPLOAD_INVALID_SCRIPT",
            f"scripts 语法错误: {path}: {exc}",
            status_code=400,
        ) from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = (alias.name or "").split(".", 1)[0]
                if base in _SCRIPT_BLACKLIST_MODULES:
                    raise AgentFactoryException(
                        "SKILL_UPLOAD_FORBIDDEN_IMPORT",
                        f"禁止的 import: {base} ({path})",
                        status_code=400,
                    )
        elif isinstance(node, ast.ImportFrom):
            base = (node.module or "").split(".", 1)[0]
            if base in _SCRIPT_BLACKLIST_MODULES:
                raise AgentFactoryException(
                    "SKILL_UPLOAD_FORBIDDEN_IMPORT",
                    f"禁止的 import: {base} ({path})",
                    status_code=400,
                )


def process_skill_tar_gz(
    data: bytes,
    *,
    skill_id: str,
    version: str,
) -> dict[str, Any]:
    """Return fields for :class:`agent_factory.db.models.skill.Skill` insert."""
    if len(data) > 50 * 1024 * 1024:
        raise AgentFactoryException(
            "FILE_TOO_LARGE",
            "tar.gz exceeds 50MB limit",
            status_code=400,
        )
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    except tarfile.TarError as exc:
        raise AgentFactoryException(
            "INVALID_FILE_TYPE",
            "Invalid tar.gz",
            status_code=400,
        ) from exc
    members = {m.name.lstrip("./") for m in tf.getmembers() if m.isfile()}
    if not any(
        n == "SKILL.md" or n.endswith("/SKILL.md") for n in members
    ):
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Skill package must contain SKILL.md at archive root",
            status_code=400,
        )
    root_prefix = ""
    skill_md_key = next(
        (n for n in sorted(members) if n == "SKILL.md" or n.endswith("/SKILL.md")),
        "SKILL.md",
    )
    if "/" in skill_md_key:
        root_prefix = skill_md_key.rsplit("/", 1)[0] + "/"

    def _full(p: str) -> str:
        return f"{root_prefix}{p}" if root_prefix else p

    extracted: dict[str, bytes] = {}
    schema_files: dict[str, Any] = {}
    script_sources: dict[str, str] = {}
    for m in tf.getmembers():
        if not m.isfile():
            continue
        name = m.name.lstrip("./")
        if root_prefix and not name.startswith(root_prefix):
            continue
        rel = name[len(root_prefix) :] if root_prefix else name
        if rel.startswith("scripts/") and rel.endswith(".py"):
            f = tf.extractfile(m)
            if f is None:
                continue
            raw = f.read()
            text = raw.decode("utf-8", errors="replace")
            _scan_script_ast(text, rel)
            script_sources[rel] = text
        if rel.startswith("schemas/") and rel.endswith(".json"):
            f = tf.extractfile(m)
            if f is None:
                continue
            raw_schema = f.read()
            try:
                schema_obj = json.loads(raw_schema.decode("utf-8"))
                if isinstance(schema_obj, dict):
                    base_name = rel.rsplit("/", 1)[-1]
                    schema_files[base_name.removesuffix(".json")] = schema_obj
            except json.JSONDecodeError:
                pass
        if rel.endswith((".md", ".txt", ".json", ".yaml", ".yml")):
            f = tf.extractfile(m)
            if f is None:
                continue
            extracted[rel] = f.read()

    skill_raw = extracted.get("SKILL.md")
    if skill_raw is None:
        for k, v in extracted.items():
            if k.endswith("SKILL.md") or k == "SKILL.md":
                skill_raw = v
                break
    if not skill_raw:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "Could not read SKILL.md",
            status_code=400,
        )
    fm, body = parse_skill_md(skill_raw.decode("utf-8", errors="replace"))
    reference_files: dict[str, str] = {}
    lazy_entries: list[dict[str, str]] = []
    file_manifest: dict[str, str] = {}
    for rel, raw in extracted.items():
        if rel == "SKILL.md" or rel.endswith("/SKILL.md"):
            continue
        text = raw.decode("utf-8", errors="replace")
        reference_files[rel] = text
        file_manifest[rel] = hashlib.sha256(raw).hexdigest()

    pkg_hash = hashlib.sha256(data).hexdigest()
    meta: dict[str, Any] = {
        "skill_body": body,
        "frontmatter": fm,
        "reference_files": reference_files,
        "lazy_refs": fm.get("lazy_refs") or fm.get("lazy_references") or [],
        "file_manifest": file_manifest,
        "schema_files": schema_files,
        "script_sources": script_sources,
        "tools": fm.get("tools") or {"require": [], "optional": []},
    }
    name = fm.get("name") if isinstance(fm, dict) else None
    return {
        "id": skill_id,
        "version": version,
        "name": str(name or skill_id)[:128],
        "description": (fm.get("description") if isinstance(fm, dict) else None),
        "when_to_use": fm.get("when_to_use") if isinstance(fm, dict) else None,
        "risk_tier": fm.get("risk_tier") if isinstance(fm, dict) else None,
        "skill_package_hash": pkg_hash,
        "package_metadata": meta,
    }
