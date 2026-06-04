"""Skill package tar.gz in object storage (docs/05 §7.7, docs/04)."""

from __future__ import annotations

import hashlib
import io
import logging
import tarfile
from typing import Any

from agent_factory.config import Settings
from agent_factory.infra.minio_client import MinioClient
from agent_factory.middleware.error_handler import AgentFactoryException

logger = logging.getLogger(__name__)


def skill_bundle_object_key(skill_id: str, version: str) -> str:
    sid = skill_id.strip().replace("/", "_")
    ver = version.strip().replace("/", "_")
    return f"skills/{sid}/{ver}/package.tar.gz"


def compute_tarball_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def put_skill_bundle(
    minio: MinioClient,
    settings: Settings,
    *,
    skill_id: str,
    version: str,
    tarball: bytes,
) -> str:
    """Upload ``.tar.gz``; return object key."""
    key = skill_bundle_object_key(skill_id, version)
    await minio.put_object(
        bucket=settings.MINIO_BUCKET,
        object_name=key,
        data=tarball,
        length=len(tarball),
        content_type="application/gzip",
    )
    return key


async def get_skill_bundle_bytes(
    minio: MinioClient,
    settings: Settings,
    storage_path: str,
) -> bytes:
    try:
        return await minio.get_object(settings.MINIO_BUCKET, storage_path)
    except Exception as exc:
        logger.warning("skill bundle get failed path=%s: %s", storage_path, exc)
        raise AgentFactoryException(
            "SKILL_BUNDLE_UNAVAILABLE",
            "Failed to load skill package from storage",
            status_code=502,
        ) from exc


def verify_bundle_hash(data: bytes, expected_hash: str | None) -> None:
    if not expected_hash:
        return
    got = compute_tarball_sha256(data)
    if got != expected_hash.strip().lower() and got != expected_hash.strip():
        raise AgentFactoryException(
            "SKILL_PACKAGE_HASH_MISMATCH",
            "Stored skill tarball hash does not match skill_package_hash",
            status_code=409,
        )


def extract_text_from_tarball(
    tarball: bytes,
    relative_path: str,
) -> str | None:
    """Read UTF-8 text for ``relative_path`` inside ``.tar.gz``."""
    rel = relative_path.lstrip("./")
    try:
        tf = tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz")
    except tarfile.TarError:
        return None
    root_prefix = ""
    members = {m.name.lstrip("./") for m in tf.getmembers() if m.isfile()}
    skill_md = next(
        (n for n in sorted(members) if n == "SKILL.md" or n.endswith("/SKILL.md")),
        None,
    )
    if skill_md and "/" in skill_md:
        root_prefix = skill_md.rsplit("/", 1)[0] + "/"

    candidates = [rel]
    if not rel.startswith("references/") and not rel.startswith("reference/"):
        candidates.extend([f"references/{rel}", f"reference/{rel}"])
    for cand in candidates:
        full = f"{root_prefix}{cand}" if root_prefix else cand
        for m in tf.getmembers():
            if not m.isfile():
                continue
            name = m.name.lstrip("./")
            if name != full and not name.endswith("/" + cand):
                continue
            f = tf.extractfile(m)
            if f is None:
                continue
            raw = f.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("utf-8", errors="replace")
    return None


def load_schema_from_metadata(
    package_metadata: dict[str, Any],
    schema_name: str,
) -> dict[str, Any] | None:
    files = package_metadata.get("schema_files")
    if not isinstance(files, dict):
        return None
    raw = files.get(schema_name) or files.get(f"{schema_name}.json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        import json

        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None
