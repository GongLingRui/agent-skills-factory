"""Skill Registry routes (docs/04, docs/19)."""

import shutil
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.api.deps_admin import (
    RegistryAuth,
    SessionOrOperatorAuth,
    require_registry_superuser,
    require_session_or_admin_operator,
    require_skill_publish,
)
from agent_factory.config import get_settings
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.db.models.skill import Skill
from agent_factory.infra.db import get_db_session
from agent_factory.infra.skill_notify import publish_skill_changed
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.infra.minio_client import MinioClient
from agent_factory.services.skill_eval_gate import run_skill_registry_eval_gate
from agent_factory.services.skill_bundle_storage import put_skill_bundle
from agent_factory.services.skill_git_import import (
    directory_to_tar_gz_bytes,
    fetch_skill_directory_from_git,
)
from agent_factory.services.skill_upload_service import process_skill_tar_gz

router = APIRouter()


async def _mounted_agents_for_skill(
    db: AsyncSession, skill_id: str
) -> list[dict[str, Any]]:
    """Agents whose ``skill_config.id`` matches ``skill_id`` (prd §8.5)."""
    sid = AgentApp.skill_config["id"].as_string()
    q = await db.execute(
        select(AgentApp.id, AgentApp.name, AgentApp.version, AgentApp.lifecycle_state)
        .where(AgentApp.skill_config.isnot(None), sid == skill_id)
        .order_by(AgentApp.id)
    )
    return [
        {
            "id": i,
            "name": n,
            "version": v,
            "lifecycle_state": lc,
        }
        for i, n, v, lc in q.all()
    ]


class SkillCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    version: str = Field(..., min_length=1, max_length=32)
    name: str | None = Field(None, max_length=128)
    description: str | None = None
    when_to_use: str | None = None
    owner: str | None = Field(None, max_length=64)
    risk_tier: str | None = Field(None, pattern="^(low|medium|high)$")
    skill_package_hash: str | None = Field(None, max_length=64)
    package_metadata: dict[str, Any] | None = None
    storage_path: str | None = Field(None, max_length=256)


class SkillUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    description: str | None = None
    when_to_use: str | None = None
    owner: str | None = Field(None, max_length=64)
    risk_tier: str | None = Field(None, pattern="^(low|medium|high)$")
    skill_package_hash: str | None = Field(None, max_length=64)
    package_metadata: dict[str, Any] | None = None
    storage_path: str | None = Field(None, max_length=256)


@router.post("")
async def create_skill(
    body: SkillCreate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[RegistryAuth, Depends(require_skill_publish)],
) -> dict[str, Any]:
    """Register a new Skill (id+version composite PK)."""
    existing = await db.execute(
        select(Skill).where(Skill.id == body.id, Skill.version == body.version)
    )
    if existing.scalar_one_or_none():
        raise AgentFactoryException(
            "CONFLICT",
            f"Skill {body.id}@{body.version} already exists",
            status_code=409,
        )

    await run_skill_registry_eval_gate(
        package_metadata=body.package_metadata,
        settings=get_settings(),
    )

    row = Skill(
        id=body.id,
        version=body.version,
        name=body.name,
        description=body.description,
        when_to_use=body.when_to_use,
        owner=body.owner,
        risk_tier=body.risk_tier,
        skill_package_hash=body.skill_package_hash,
        package_metadata=body.package_metadata,
        storage_path=body.storage_path,
        status="active",
    )
    db.add(row)
    await db.flush()
    await publish_skill_changed(
        skill_id=row.id, version=row.version, action="created"
    )
    return {
        "id": row.id,
        "version": row.version,
        "status": row.status,
    }


@router.post("/upload")
async def upload_skill_tar_gz(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[RegistryAuth, Depends(require_skill_publish)],
    file: UploadFile = File(...),
    skill_id: str = Form(..., min_length=1, max_length=64),
    version: str = Form(..., min_length=1, max_length=32),
) -> dict[str, Any]:
    """Upload ``.tar.gz`` Skill bundle (docs/19 backlog)."""
    raw = await file.read()
    if not raw.startswith(b"\x1f\x8b"):
        raise AgentFactoryException(
            "INVALID_FILE_TYPE",
            "Expected gzip-compressed tar (.tar.gz)",
            status_code=400,
        )
    payload = process_skill_tar_gz(raw, skill_id=skill_id.strip(), version=version.strip())
    await run_skill_registry_eval_gate(
        package_metadata=payload["package_metadata"],
        settings=get_settings(),
    )
    existing = await db.execute(
        select(Skill).where(Skill.id == payload["id"], Skill.version == payload["version"])
    )
    if existing.scalar_one_or_none():
        raise AgentFactoryException(
            "CONFLICT",
            f"Skill {payload['id']}@{payload['version']} already exists",
            status_code=409,
        )
    settings = get_settings()
    storage_path: str | None = None
    try:
        minio = MinioClient(settings)
        storage_path = await put_skill_bundle(
            minio,
            settings,
            skill_id=payload["id"],
            version=payload["version"],
            tarball=raw,
        )
    except Exception:
        pass

    row = Skill(
        id=payload["id"],
        version=payload["version"],
        name=payload.get("name"),
        description=payload.get("description"),
        when_to_use=payload.get("when_to_use"),
        risk_tier=payload.get("risk_tier"),
        skill_package_hash=payload.get("skill_package_hash"),
        package_metadata=payload.get("package_metadata"),
        storage_path=storage_path,
        status="active",
    )
    db.add(row)
    await db.flush()
    await publish_skill_changed(
        skill_id=row.id, version=row.version, action="created"
    )
    await db.commit()
    return {
        "id": row.id,
        "version": row.version,
        "status": row.status,
        "storage_path": storage_path,
    }


class SkillGitImport(BaseModel):
    git_url: str = Field(..., min_length=8, max_length=512)
    skill_id: str = Field(..., min_length=1, max_length=64)
    version: str = Field(..., min_length=1, max_length=32)
    ref: str = Field(default="HEAD", max_length=128)


@router.post("/import-git")
async def import_skill_from_git(
    body: SkillGitImport,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[RegistryAuth, Depends(require_skill_publish)],
) -> dict[str, Any]:
    """Clone git repo and register Skill (docs/04 §8.5)."""
    settings = get_settings()
    if not settings.SKILL_GIT_IMPORT_ENABLED:
        raise AgentFactoryException(
            "FEATURE_DISABLED",
            "git skill import is disabled",
            status_code=403,
        )
    repo_dir = fetch_skill_directory_from_git(body.git_url, ref=body.ref)
    try:
        raw = directory_to_tar_gz_bytes(repo_dir)
    finally:
        shutil.rmtree(repo_dir.parent, ignore_errors=True)

    payload = process_skill_tar_gz(
        raw,
        skill_id=body.skill_id.strip(),
        version=body.version.strip(),
    )
    await run_skill_registry_eval_gate(
        package_metadata=payload["package_metadata"],
        settings=settings,
    )
    existing = await db.execute(
        select(Skill).where(Skill.id == payload["id"], Skill.version == payload["version"])
    )
    if existing.scalar_one_or_none():
        raise AgentFactoryException(
            "CONFLICT",
            f"Skill {payload['id']}@{payload['version']} already exists",
            status_code=409,
        )
    storage_path: str | None = None
    try:
        minio = MinioClient(settings)
        storage_path = await put_skill_bundle(
            minio,
            settings,
            skill_id=payload["id"],
            version=payload["version"],
            tarball=raw,
        )
    except Exception:
        pass
    row = Skill(
        id=payload["id"],
        version=payload["version"],
        name=payload.get("name"),
        description=payload.get("description"),
        when_to_use=payload.get("when_to_use"),
        risk_tier=payload.get("risk_tier"),
        skill_package_hash=payload.get("skill_package_hash"),
        package_metadata=payload.get("package_metadata"),
        storage_path=storage_path,
        status="active",
    )
    db.add(row)
    await db.flush()
    await publish_skill_changed(
        skill_id=row.id, version=row.version, action="created"
    )
    await db.commit()
    return {
        "id": row.id,
        "version": row.version,
        "status": row.status,
        "storage_path": storage_path,
    }


@router.get("")
async def list_skills(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[SessionOrOperatorAuth, Depends(require_session_or_admin_operator)],
) -> dict[str, Any]:
    """List active skills."""
    q = await db.execute(
        select(Skill)
        .where(Skill.status == "active")
        .order_by(Skill.id, Skill.version)
    )
    rows = q.scalars().all()
    return {
        "skills": [
            {
                "id": s.id,
                "version": s.version,
                "name": s.name,
                "description": s.description,
                "risk_tier": s.risk_tier,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in rows
        ]
    }


@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[SessionOrOperatorAuth, Depends(require_session_or_admin_operator)],
    version: str | None = None,
) -> dict[str, Any]:
    """Skill detail. If version omitted, return all versions."""
    if version:
        row = await db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.version == version)
        )
        s = row.scalar_one_or_none()
        if s is None:
            raise AgentFactoryException(
                "SKILL_NOT_FOUND", "Skill not found", status_code=404
            )
        mounted = await _mounted_agents_for_skill(db, skill_id)
        return {
            "id": s.id,
            "version": s.version,
            "name": s.name,
            "description": s.description,
            "when_to_use": s.when_to_use,
            "owner": s.owner,
            "risk_tier": s.risk_tier,
            "skill_package_hash": s.skill_package_hash,
            "package_metadata": s.package_metadata,
            "storage_path": s.storage_path,
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "mounted_agents": mounted,
        }

    q = await db.execute(
        select(Skill).where(Skill.id == skill_id).order_by(Skill.version)
    )
    rows = q.scalars().all()
    if not rows:
        raise AgentFactoryException(
            "SKILL_NOT_FOUND", "Skill not found", status_code=404
        )
    mounted = await _mounted_agents_for_skill(db, skill_id)
    return {
        "id": skill_id,
        "versions": [
            {
                "version": s.version,
                "name": s.name,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in rows
        ],
        "mounted_agents": mounted,
    }


@router.put("/{skill_id}")
async def update_skill(
    skill_id: str,
    body: SkillUpdate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[RegistryAuth, Depends(require_skill_publish)],
    version: str = "latest",
) -> dict[str, Any]:
    """Update a skill version (default latest active)."""
    if version == "latest":
        q = await db.execute(
            select(Skill)
            .where(Skill.id == skill_id, Skill.status == "active")
            .order_by(Skill.version.desc())
        )
        row = q.scalars().first()
    else:
        q = await db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.version == version)
        )
        row = q.scalar_one_or_none()

    if row is None:
        raise AgentFactoryException(
            "SKILL_NOT_FOUND", "Skill not found", status_code=404
        )

    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.when_to_use is not None:
        row.when_to_use = body.when_to_use
    if body.owner is not None:
        row.owner = body.owner
    if body.risk_tier is not None:
        row.risk_tier = body.risk_tier
    if body.skill_package_hash is not None:
        row.skill_package_hash = body.skill_package_hash
    if body.storage_path is not None:
        row.storage_path = body.storage_path
    if body.package_metadata is not None:
        merged = {**(row.package_metadata or {}), **body.package_metadata}
        await run_skill_registry_eval_gate(
            package_metadata=merged,
            settings=get_settings(),
        )
        row.package_metadata = merged

    await publish_skill_changed(skill_id=row.id, version=row.version, action="updated")
    return {"id": row.id, "version": row.version, "status": "updated"}


@router.delete("/{skill_id}")
async def deprecate_skill(
    skill_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _auth: Annotated[RegistryAuth, Depends(require_registry_superuser)],
    version: str | None = None,
) -> dict[str, Any]:
    """Deprecate a skill (mark status=deprecated, never delete)."""
    if version:
        q = await db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.version == version)
        )
        row = q.scalar_one_or_none()
    else:
        q = await db.execute(
            select(Skill)
            .where(Skill.id == skill_id, Skill.status == "active")
            .order_by(Skill.version.desc())
        )
        row = q.scalars().first()

    if row is None:
        raise AgentFactoryException(
            "SKILL_NOT_FOUND", "Skill not found", status_code=404
        )

    row.status = "deprecated"
    await publish_skill_changed(
        skill_id=row.id,
        version=row.version,
        action="deprecated",
    )
    return {"id": row.id, "version": row.version, "status": "deprecated"}
