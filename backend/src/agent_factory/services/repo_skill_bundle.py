"""Build Skill Registry ``package_metadata`` from a Skill 包目录树。

典型落盘为 ``agents/<agent>/skill/``（见 prd.md 第五节）；亦兼容任意含
``SKILL.md`` 的包目录。将 Claude 风格 SKILL.md + ``references/`` + ``assets/``
映射为 :func:`agent_factory.services.skill_payload.skill_orm_to_compiler_pkg`
与 ``read_reference`` 使用的字段（``reference_files``、``lazy_refs``、
``file_manifest`` 等）。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)$",
    re.DOTALL | re.MULTILINE,
)

_TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".txt",
        ".html",
        ".htm",
        ".js",
        ".css",
        ".json",
        ".yaml",
        ".yml",
        ".svg",
    }
)


def parse_skill_md(text: str) -> tuple[dict[str, Any], str]:
    """Split SKILL.md into YAML frontmatter dict and markdown body."""
    m = _FRONTMATTER_RE.match(text.strip("\ufeff"))
    if not m:
        return {}, text.strip()
    raw_fm, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body.strip()


def _posix_rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _unique_lazy_name(rel_posix: str, stem: str, used: dict[str, str]) -> str:
    """Return a ``read_reference`` name; prefer ``stem`` if unambiguous."""
    if stem not in used:
        used[stem] = rel_posix
        return stem
    if used.get(stem) == rel_posix:
        return stem
    parent = Path(rel_posix).parent.name
    candidate = f"{stem}_{parent}" if parent else f"{stem}_alt"
    n = 2
    while candidate in used and used[candidate] != rel_posix:
        candidate = f"{stem}_{parent}_{n}" if parent else f"{stem}_alt_{n}"
        n += 1
    used[candidate] = rel_posix
    return candidate


def collect_repo_skill_files(skill_root: Path) -> tuple[dict[str, str], list[dict[str, str]], dict[str, str]]:
    """Walk bundle files: reference text, lazy ref index, path -> sha256 manifest."""
    reference_files: dict[str, str] = {}
    file_manifest: dict[str, str] = {}
    lazy_entries: list[dict[str, str]] = []
    used_names: dict[str, str] = {}

    for path in sorted(skill_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "SKILL.md":
            continue
        if path.name.startswith("."):
            continue
        if "__pycache__" in path.parts:
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        rel = _posix_rel(skill_root, path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        reference_files[rel] = text
        file_manifest[rel] = _sha256_text(text)
        stem = path.stem
        name = _unique_lazy_name(rel, stem, used_names)
        lazy_entries.append({"name": name, "path": rel})

    lazy_entries.sort(key=lambda x: x["path"])
    return reference_files, lazy_entries, file_manifest


def compute_skill_package_hash(
    *,
    skill_id: str,
    skill_version: str,
    skill_body: str,
    file_manifest: dict[str, str],
) -> str:
    """Same canonical payload as :mod:`agent_factory.core.compiler` (prd §7.7)."""
    sorted_fm = {k: file_manifest[k] for k in sorted(file_manifest.keys())}
    payload: dict[str, Any] = {
        "file_manifest": sorted_fm,
        "skill_body": skill_body,
        "skill_id": skill_id,
        "skill_version": skill_version,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _coerce_tool_id_list(value: Any) -> list[str]:
    """Normalize a YAML list of tool ids to non-empty strings."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for x in value:
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def tools_from_skill_frontmatter(fm: dict[str, Any]) -> dict[str, list[str]]:
    """Build ``package_metadata.tools`` from SKILL.md frontmatter.

    When ``tools`` is absent or invalid, return empty require/optional so
    Compiler does not intersect away agent-declared tools (see
    :func:`agent_factory.core.permissions.intersect_tools`).

    Optional frontmatter (docs/04-skill-package-spec.md)::

        tools:
          require: [doc.extract]
          optional: [read_reference]
    """
    raw = fm.get("tools")
    if not isinstance(raw, dict):
        return {"require": [], "optional": []}
    return {
        "require": _coerce_tool_id_list(raw.get("require")),
        "optional": _coerce_tool_id_list(raw.get("optional")),
    }


def minimal_eval_cases(skill_id: str) -> list[dict[str, Any]]:
    """One schema-valid case so ``SKILL_EVAL_CASES_REQUIRED`` passes (docs/04)."""
    return [
        {
            "id": f"{skill_id}-registry-smoke",
            "name": "registry smoke",
            "input": {
                "message": (
                    "请用一句话确认你已加载本 Skill 的核心角色与边界，"
                    "不要展开执行流程。"
                ),
            },
            "min_score": 0.0,
        }
    ]


def build_package_metadata_for_skill_dir(
    *,
    skill_id: str,
    skill_body: str,
    reference_files: dict[str, str],
    lazy_refs: list[dict[str, str]],
    file_manifest: dict[str, str],
    tools: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Assemble JSONB ``package_metadata`` for create/update API."""
    tools_meta = tools if tools is not None else {"require": [], "optional": []}
    return {
        "skill_instruction": skill_body,
        "tools": tools_meta,
        "knowledge_scopes": {"suggest": []},
        "enterprise": {"risk_tier": "low"},
        "lazy_refs": lazy_refs,
        "indexed_refs": [],
        "always_refs": [],
        "reference_files": reference_files,
        "file_manifest": file_manifest,
        "eval_cases": minimal_eval_cases(skill_id),
    }


def load_skill_bundle_from_directory(
    skill_root: Path,
    *,
    version: str = "0.1.0",
    storage_path: str | None = None,
) -> dict[str, Any]:
    """Parse a Skill 包目录（含 ``SKILL.md``）为 ``SkillCreate`` JSON。"""
    skill_md = skill_root / "SKILL.md"
    if not skill_md.is_file():
        raise ValueError(f"Missing SKILL.md under {skill_root}")
    fm, body = parse_skill_md(skill_md.read_text(encoding="utf-8"))
    sid = str(fm.get("name") or skill_root.name).strip()
    if not sid:
        sid = skill_root.name
    name = fm.get("name")
    title = str(name).strip() if isinstance(name, str) else sid
    desc = fm.get("description")
    when = fm.get("when_to_use")
    description = str(desc).strip() if isinstance(desc, str) else ""
    when_to_use = str(when).strip() if isinstance(when, str) else ""

    ref_files, lazy_refs, manifest = collect_repo_skill_files(skill_root)
    pkg_meta = build_package_metadata_for_skill_dir(
        skill_id=sid,
        skill_body=body,
        reference_files=ref_files,
        lazy_refs=lazy_refs,
        file_manifest=manifest,
        tools=tools_from_skill_frontmatter(fm),
    )
    pkg_hash = compute_skill_package_hash(
        skill_id=sid,
        skill_version=version,
        skill_body=body,
        file_manifest=manifest,
    )
    if storage_path is not None and storage_path.strip():
        storage_posix = storage_path.strip().replace("\\", "/")
    else:
        storage_posix = Path("skills") / sid
        storage_posix = storage_posix.as_posix()
    return {
        "id": sid,
        "version": version,
        "name": title,
        "description": description,
        "when_to_use": when_to_use,
        "owner": "repo",
        "risk_tier": "low",
        "skill_package_hash": pkg_hash,
        "storage_path": storage_posix,
        "package_metadata": pkg_meta,
    }
