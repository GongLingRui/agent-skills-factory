"""Tests for Tool Gateway."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_factory.db.models.file_upload import FileUpload
from agent_factory.db.models.run_spec import RunSpec
from agent_factory.db.models.skill import Skill
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.tool_gateway import ToolGateway


def test_validate_and_run_allowed():
    gw = ToolGateway()
    result = gw.validate_and_run(
        tool_id="kb.search",
        params={"query": "test"},
        allowed_tools=["kb.search"],
        retrieval_scopes=[],
    )
    assert "results" in result


def test_risk_rule_check_engine():
    gw = ToolGateway()
    out = gw.validate_and_run(
        tool_id="risk.rule_check",
        params={"text": "双方同意放弃追索违约金"},
        allowed_tools=["risk.rule_check"],
        retrieval_scopes=[],
    )
    assert out["risk_level"] == "medium"
    assert out["requires_human_review"] is True


@pytest.mark.asyncio
async def test_risk_rule_check_async_builtin():
    gw = ToolGateway()
    out = await gw._handle_risk_rule_check_async(
        params={"text": "普通条款"},
        retrieval_scopes=[],
    )
    assert out["engine"] == "builtin"
    assert "risk_level" in out


def test_risk_rule_check_requires_text():
    gw = ToolGateway()
    with pytest.raises(AgentFactoryException) as exc_info:
        gw.validate_and_run(
            tool_id="risk.rule_check",
            params={},
            allowed_tools=["risk.rule_check"],
            retrieval_scopes=[],
        )
    assert exc_info.value.code == "INVALID_PARAMS"


def test_validate_and_run_not_allowed():
    gw = ToolGateway()
    with pytest.raises(AgentFactoryException) as exc_info:
        gw.validate_and_run(
            tool_id="kb.search",
            params={},
            allowed_tools=["doc.extract"],
            retrieval_scopes=[],
        )
    assert exc_info.value.code == "TOOL_NOT_ALLOWED"


def test_doc_extract_requires_file_id():
    gw = ToolGateway()
    with pytest.raises(AgentFactoryException) as exc_info:
        gw.validate_and_run(
            tool_id="doc.extract",
            params={},
            allowed_tools=["doc.extract"],
            retrieval_scopes=[],
        )
    assert exc_info.value.code == "INVALID_PARAMS"


def test_read_reference_sync_stub_requires_name():
    gw = ToolGateway()
    with pytest.raises(AgentFactoryException) as exc_info:
        gw.validate_and_run(
            tool_id="read_reference",
            params={},
            allowed_tools=["read_reference"],
            retrieval_scopes=[],
        )
    assert exc_info.value.code == "INVALID_PARAMS"


def test_read_reference_sync_stub_with_name():
    gw = ToolGateway()
    out = gw.validate_and_run(
        tool_id="read_reference",
        params={"name": "x"},
        allowed_tools=["read_reference"],
        retrieval_scopes=[],
    )
    assert out["name"] == "x"
    assert "stub" in out["content"].lower()


@pytest.mark.asyncio
async def test_doc_extract_async_loads_minio_text():
    fu = FileUpload(
        file_id="file_x",
        session_id="sess1",
        user_id_hash="uh",
        file_name="a.txt",
        file_size=3,
        mime_type="text/plain",
        sha256="",
        storage_path="orig/a",
        status="extracted",
        extracted_text_path="temp/sess1/extract_file_x.txt",
        created_at=None,
        expires_at=None,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fu
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    class _FakeMinio:
        def __init__(self, *_a, **_k) -> None:
            pass

        async def get_object(self, _bucket: str, _path: str) -> bytes:
            return b"extracted-body"

    gw = ToolGateway()
    with patch(
        "agent_factory.services.tool_gateway.MinioClient",
        _FakeMinio,
    ):
        out = await gw.validate_and_run_async(
            mock_db,
            tool_id="doc.extract",
            params={"file_id": "file_x"},
            allowed_tools=["doc.extract"],
            retrieval_scopes=[],
        )
    assert out["file_id"] == "file_x"
    assert out["text"] == "extracted-body"
    assert out["pages"] == 1


@pytest.mark.asyncio
async def test_read_reference_async_ok():
    rs = RunSpec(
        run_id="run_t",
        runspec_schema_version=1,
        agent_id="ag",
        agent_version="1",
        skill_id="sk1",
        skill_version="1.0.0",
        skill_package_hash="",
        user_id_hash="u",
        skill_file_manifest={},
        lazy_references=[{"name": "note", "path": "references/note.md"}],
        allowed_tools=["read_reference"],
    )
    meta = {"reference_files": {"references/note.md": "NOTE BODY"}}
    skill = Skill(
        id="sk1",
        version="1.0.0",
        name="S",
        description=None,
        when_to_use=None,
        owner=None,
        risk_tier="low",
        skill_package_hash=None,
        package_metadata=meta,
        storage_path=None,
        status="active",
        deprecated_at=None,
        deprecated_by=None,
        created_at=None,
        created_by=None,
    )
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = skill
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mr)

    gw = ToolGateway()
    out = await gw.validate_and_run_async(
        mock_db,
        tool_id="read_reference",
        params={"name": "note"},
        allowed_tools=["read_reference"],
        retrieval_scopes=[],
        run_spec=rs,
    )
    assert out["content"] == "NOTE BODY"
    assert out["name"] == "note"


@pytest.mark.asyncio
async def test_read_reference_async_requires_run_spec():
    gw = ToolGateway()
    mock_db = AsyncMock()
    with pytest.raises(AgentFactoryException) as ei:
        await gw.validate_and_run_async(
            mock_db,
            tool_id="read_reference",
            params={"name": "x"},
            allowed_tools=["read_reference"],
            retrieval_scopes=[],
        )
    assert ei.value.code == "RUNSPEC_REQUIRED"


@pytest.mark.asyncio
async def test_read_reference_async_rejects_unknown_name():
    rs = RunSpec(
        run_id="run_u",
        runspec_schema_version=1,
        agent_id="ag",
        agent_version="1",
        skill_id="sk1",
        skill_version="1.0.0",
        skill_package_hash="",
        user_id_hash="u",
        lazy_references=[{"name": "only", "path": "references/only.md"}],
        allowed_tools=["read_reference"],
    )
    mock_db = AsyncMock()
    skill_row = MagicMock()
    skill_row.package_metadata = {}
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = skill_row
    mock_db.execute = AsyncMock(return_value=mock_result)
    gw = ToolGateway()
    with pytest.raises(AgentFactoryException) as ei:
        await gw.validate_and_run_async(
            mock_db,
            tool_id="read_reference",
            params={"name": "other"},
            allowed_tools=["read_reference"],
            retrieval_scopes=[],
            run_spec=rs,
        )
    assert ei.value.code == "REFERENCE_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_doc_extract_async_pending_inline_plain_text():
    fu = FileUpload(
        file_id="file_y",
        session_id="sess1",
        user_id_hash="uh",
        file_name="note.txt",
        file_size=12,
        mime_type="text/plain",
        sha256="",
        storage_path="orig/b",
        status="pending",
        extracted_text_path=None,
        created_at=None,
        expires_at=None,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fu
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()

    class _FakeMinio:
        def __init__(self, *_a, **_k) -> None:
            pass

        async def get_object(self, *_a, **_k) -> bytes:
            return b"hello from upload"

        async def put_object(self, **_k) -> None:
            return None

    gw = ToolGateway()
    with patch(
        "agent_factory.services.tool_gateway.MinioClient",
        _FakeMinio,
    ):
        out = await gw.validate_and_run_async(
            mock_db,
            tool_id="doc.extract",
            params={"file_id": "file_y"},
            allowed_tools=["doc.extract"],
            retrieval_scopes=[],
        )
    assert out["pages"] == 1
    assert "hello from upload" in out["text"]
    mock_db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_doc_extract_async_pending_no_storage_path():
    fu = FileUpload(
        file_id="file_z",
        session_id="sess1",
        user_id_hash="uh",
        file_name="x.pdf",
        file_size=3,
        mime_type="application/pdf",
        sha256="",
        storage_path=None,
        status="pending",
        extracted_text_path=None,
        created_at=None,
        expires_at=None,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fu
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    gw = ToolGateway()
    out = await gw.validate_and_run_async(
        mock_db,
        tool_id="doc.extract",
        params={"file_id": "file_z"},
        allowed_tools=["doc.extract"],
        retrieval_scopes=[],
    )
    assert out["pages"] == 0
    assert "not stored" in out["text"].lower()
