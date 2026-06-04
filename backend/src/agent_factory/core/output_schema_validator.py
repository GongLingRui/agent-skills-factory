"""JSON Schema validation for model output (docs/08)."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_factory.core.model_output_parse import extract_json_object_from_text

logger = logging.getLogger(__name__)

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    jsonschema = None  # type: ignore[assignment]
    Draft202012Validator = None  # type: ignore[misc, assignment]


@lru_cache(maxsize=64)
def _validator_for_schema(schema_json: str) -> Any:
    if Draft202012Validator is None:
        raise RuntimeError("jsonschema not installed")
    schema = json.loads(schema_json)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_json_against_schema(
    instance: dict[str, Any],
    schema: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Return (ok, error_messages)."""
    if jsonschema is None:
        return True, []
    try:
        v = Draft202012Validator(schema)
        errors = sorted(v.iter_errors(instance), key=lambda e: e.path)
        if not errors:
            return True, []
        msgs = [e.message for e in errors[:8]]
        return False, msgs
    except Exception as exc:
        logger.warning("schema validation internal error: %s", exc)
        return False, [str(exc)]


def load_agent_schema_file(
    repo_root: Path,
    agent_id: str,
    schema_name: str,
) -> dict[str, Any] | None:
    path = repo_root / "agents" / agent_id / "schemas" / f"{schema_name}.json"
    if not path.is_file():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def resolve_output_schema(
    *,
    schema_name: str | None,
    agent_id: str | None,
    package_metadata: dict[str, Any] | None,
    repo_root: Path | None = None,
) -> dict[str, Any] | None:
    if not schema_name:
        return None
    if repo_root and agent_id:
        agent_schema = load_agent_schema_file(repo_root, agent_id, schema_name)
        if agent_schema is not None:
            return agent_schema
    if package_metadata:
        from agent_factory.services.skill_bundle_storage import (
            load_schema_from_metadata,
        )

        meta_schema = load_schema_from_metadata(package_metadata, schema_name)
        if meta_schema is not None:
            return meta_schema
    return None


def output_matches_schema_constraint(
    text: str,
    *,
    schema_name: str | None,
    agent_id: str | None = None,
    package_metadata: dict[str, Any] | None = None,
    repo_root: Path | None = None,
) -> bool | None:
    """Industrial validation: parse JSON + jsonschema when schema resolvable."""
    if not schema_name:
        return None
    schema = resolve_output_schema(
        schema_name=schema_name,
        agent_id=agent_id,
        package_metadata=package_metadata,
        repo_root=repo_root,
    )
    obj = extract_json_object_from_text(text)
    if obj is None:
        try:
            obj = json.loads(text.strip())
            if not isinstance(obj, dict):
                return False
        except json.JSONDecodeError:
            return False
    if schema is None:
        return True
    ok, _errs = validate_json_against_schema(obj, schema)
    return ok
