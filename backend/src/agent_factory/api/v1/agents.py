"""Agent routes: list, detail, init, chat SSE, resume, upload, feedback."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.api.deps import (
    get_current_user,
    get_current_user_or_operator,
    redis_dep,
)
from agent_factory.config import get_settings
from agent_factory.core.attachment_policy import (
    MAGIC_SNIFF_BYTES,
    validate_upload_for_ui_config,
)
from agent_factory.core.filename_sanitize import sanitize_upload_filename
from agent_factory.core.prompt_risk import prompt_injection_risk_score
from agent_factory.core.rbac import effective_permissions
from agent_factory.core.text_sanitize import strip_format_and_control_chars
from agent_factory.core.user_context import UserContext
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.db.models.audit import AgentUsageLog, FeedbackLog
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.db.models.file_upload import FileUpload
from agent_factory.db.models.run_spec import RunSpec
from agent_factory.infra.db import get_db_session, get_session_factory
from agent_factory.infra.doc_queue import (
    doc_parse_queue_depth,
    enqueue_doc_parse_job,
)
from agent_factory.infra.minio_client import MinioClient
from agent_factory.infra.model_queue import (
    ModelQueuePolicyError,
    preflight_model_queue_or_raise,
)
from agent_factory.infra.model_runtime_signals import (
    read_latency_ema_ms,
    read_latency_p99_ms,
    window_error_rate,
)
from agent_factory.infra.tool_circuit_breaker import any_http_tool_circuit_open
from agent_factory.infra.redis import Redis
from agent_factory.infra.session_lock import (
    acquire_session_lock_or_wait,
    release_session_lock,
)
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services import quota_service as qsvc
from agent_factory.services.agent_disable import is_agent_disabled
from agent_factory.services.audit_service import push_audit_event, set_audit_elevation
from agent_factory.services.auth_service import fetch_revoke_gen_snapshot
from agent_factory.services.compiler_service import CompilerService
from agent_factory.services.degradation_runtime import (
    build_degradation_run_knobs,
    filter_allowed_tools_under_circuit,
)
from agent_factory.services.degradation_service import (
    DegradationService,
    widget_degradation_hint,
)
from agent_factory.services.factory import get_model_gateway, get_tool_gateway
from agent_factory.services.runner_service import (
    RunnerService,
    _resolve_model_queue_context,
)
from agent_factory.services.session_memory import load_latest_session_memory
from agent_factory.services.user_agent_memory_service import fetch_cross_session_summary

logger = logging.getLogger(__name__)

router = APIRouter()


class InitBody(BaseModel):
    session_id: str | None = None
    """Optional logical model id (``models.yaml`` key or ``model_aliases``)."""
    model: str | None = Field(None, max_length=128)


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=120000)
    session_id: str = Field(..., min_length=1)
    file_ids: list[str] = Field(default_factory=list)


class ResumeBody(BaseModel):
    session_id: str = Field(..., min_length=1)
    checkpoint_id: str | None = None


class FeedbackBody(BaseModel):
    session_id: str = Field(..., min_length=1)
    message_id: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    feedback: str = Field(..., pattern="^(thumbs_up|thumbs_down)$")
    reasons: list[str] = []
    comment: str = Field("", max_length=200)


class TaskCreateBody(BaseModel):
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=120000)
    file_ids: list[str] = Field(default_factory=list)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _body_sha256_hex(contents: bytes) -> str:
    """SHA-256 hex digest for ``file_uploads.sha256`` (docs/39)."""
    return hashlib.sha256(contents).hexdigest()


@router.get("")
async def list_agents(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[UserContext, Depends(get_current_user_or_operator)],
) -> dict[str, Any]:
    """Agents the user may open (portal ``allowed_agents`` when present)."""
    q = await db.execute(
        select(AgentApp)
        .where(AgentApp.lifecycle_state == "active")
        .order_by(AgentApp.id)
    )
    rows = q.scalars().all()
    allowed = user.allowed_agents
    if allowed is not None:
        allow_set = set(allowed)
        rows = [a for a in rows if a.id in allow_set]
    agents = []
    for a in rows:
        ui = a.ui_config if isinstance(a.ui_config, dict) else {}
        avatar = ui.get("avatar")
        tags = a.tags if isinstance(a.tags, list) else ([] if a.tags is None else [])
        agents.append(
            {
                "id": a.id,
                "name": a.name,
                "avatar": avatar,
                "description": a.description or "",
                "tags": tags,
            }
        )
    return {"agents": agents}


@router.get("/catalog/models")
async def list_configured_models(
    _user: Annotated[UserContext, Depends(get_current_user_or_operator)],
) -> dict[str, Any]:
    """OpenAI-compatible routes for widget model picker (docs/10)."""
    gw = get_model_gateway()
    return {
        "models": gw.list_model_catalog(),
        "aliases": gw.list_model_aliases(),
        "default_model": gw.default_chat_model(),
    }


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
    _user: Annotated[UserContext, Depends(get_current_user_or_operator)],
) -> dict[str, Any]:
    q = await db.execute(select(AgentApp).where(AgentApp.id == agent_id))
    row = q.scalar_one_or_none()
    if row is None:
        raise AgentFactoryException(
            "AGENT_NOT_FOUND",
            f"Agent not found: {agent_id}",
            status_code=404,
        )
    if row.lifecycle_state != "active":
        raise AgentFactoryException(
            "AGENT_INACTIVE",
            "Agent is not active",
            status_code=403,
        )
    disabled, _reason = await is_agent_disabled(redis, agent_id)
    if disabled:
        raise AgentFactoryException(
            "AGENT_DISABLED",
            "Agent temporarily disabled by operator",
            status_code=403,
        )
    ui: dict[str, Any] = (
        row.ui_config if isinstance(row.ui_config, dict) else {}
    )
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description or "",
        "ui_config": ui,
    }


async def _init_or_resume_session(
    agent_id: str,
    body: InitBody,
    request: Request,
    db: AsyncSession,
    redis: Redis,
    user: UserContext,
    *,
    reuse_cookie: bool,
) -> dict[str, Any]:
    """Compile RunSpec, bind session, write MAU (shared by /init and /new-session)."""
    s = get_settings()

    q = await db.execute(select(AgentApp).where(AgentApp.id == agent_id))
    agent = q.scalar_one_or_none()
    if agent is None:
        raise AgentFactoryException(
            "AGENT_NOT_FOUND", f"Agent not found: {agent_id}", status_code=404
        )
    if agent.lifecycle_state != "active":
        raise AgentFactoryException(
            "AGENT_INACTIVE", "Agent is not active", status_code=403
        )

    disabled, _reason = await is_agent_disabled(redis, agent_id)
    if disabled:
        raise AgentFactoryException(
            "AGENT_DISABLED",
            "Agent temporarily disabled by operator",
            status_code=403,
        )

    if reuse_cookie:
        sid = body.session_id or request.cookies.get(s.SESSION_COOKIE_NAME)
    else:
        sid = body.session_id

    session = None
    if sid:
        q_sess = await db.execute(
            select(ChatSession).where(ChatSession.session_id == sid)
        )
        session = q_sess.scalar_one_or_none()

    compiler = CompilerService(s)
    runtime_overrides: dict[str, Any] | None = None
    if body.model and str(body.model).strip():
        gw = get_model_gateway()
        choice = str(body.model).strip()
        if not gw.is_logical_model_configured(choice):
            raise AgentFactoryException(
                "INVALID_MODEL",
                f"Unknown or unconfigured model: {choice!r}",
                status_code=400,
            )
        resolved = gw.resolve_model(choice)
        runtime_overrides = {"model": resolved}
    run_spec = await compiler.compile_and_save(
        db=db,
        agent_id=agent_id,
        user_ctx=user,
        runtime_overrides=runtime_overrides,
    )

    rev_snap = await fetch_revoke_gen_snapshot(redis, user.user_id_hash)
    perm_list = list(user.permissions)
    aa_list = list(user.allowed_agents) if user.allowed_agents is not None else None
    if session is None:
        sid = f"sess_{uuid.uuid4().hex}"
        session = ChatSession(
            session_id=sid,
            run_id=run_spec.run_id,
            user_id_hash=user.user_id_hash,
            agent_id=agent_id,
            department=user.department,
            status="running",
            turn_count=0,
            total_tokens=0,
            created_at=_utc_now(),
            last_activity=_utc_now(),
            expires_at=_utc_now().replace(hour=23, minute=59, second=59),
            allowed_agents=aa_list,
            data_domains=(
                list(user.data_domains)
                if user.data_domains is not None
                else None
            ),
            permissions=perm_list,
            revoke_gen_seen=rev_snap,
        )
        db.add(session)
    else:
        session.run_id = run_spec.run_id
        session.agent_id = agent_id
        session.status = "running"
        session.last_activity = _utc_now()
        session.permissions = perm_list
        session.revoke_gen_seen = rev_snap
        if user.allowed_agents is not None:
            session.allowed_agents = aa_list
        session.data_domains = (
            list(user.data_domains) if user.data_domains is not None else None
        )

    # Pre-fetch memory into runtime_context for fast first-turn startup
    try:
        prefetched_xs = await fetch_cross_session_summary(
            db,
            user_id_hash=session.user_id_hash,
            agent_id=session.agent_id or run_spec.agent_id,
        )
        prefetched_sm = (
            await load_latest_session_memory(db, session.run_id)
            if session.run_id
            else None
        )
        session.runtime_context = {
            "cross_session_summary": prefetched_xs,
            "session_memory": prefetched_sm.model_dump() if prefetched_sm else None,
        }
    except Exception:
        logger.exception("memory_prefetch_skipped")
        # SQL failure aborts the PostgreSQL transaction; rollback so
        # subsequent flushes run in a clean transaction.
        await db.rollback()

    await db.flush()

    today = date.today()
    mau = AgentUsageLog(
        user_id_hash=user.user_id_hash,
        agent_id=agent_id,
        usage_date=today,
        count=1,
        retention_until=_utc_now().replace(year=_utc_now().year + 1),
    )
    db.add(mau)
    await db.flush()

    ui: dict[str, Any] = (
        agent.ui_config if isinstance(agent.ui_config, dict) else {}
    )
    deg_svc = DegradationService()
    deg_state = await deg_svc.get_level()
    rt = run_spec.runtime if isinstance(run_spec.runtime, dict) else {}
    gw = get_model_gateway()
    return {
        "session_id": session.session_id,
        "run_id": run_spec.run_id,
        "ui_config": ui,
        "runtime_model": rt.get("model"),
        "available_models": gw.list_model_catalog(),
        "model_aliases": gw.list_model_aliases(),
        "degradation": {
            "level": deg_state.level,
            "reason": deg_state.reason,
            "hint": widget_degradation_hint(deg_state.level, deg_state.reason),
        },
    }


@router.post("/{agent_id}/init")
async def init_session(
    agent_id: str,
    body: InitBody,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
    user: Annotated[UserContext, Depends(get_current_user)],
) -> dict[str, Any]:
    """Initialize chat session: compile RunSpec, bind to session, write MAU."""
    return await _init_or_resume_session(
        agent_id,
        body,
        request,
        db,
        redis,
        user,
        reuse_cookie=True,
    )


@router.post("/{agent_id}/new-session")
async def new_session(
    agent_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
    user: Annotated[UserContext, Depends(get_current_user)],
    model: str | None = Query(None, max_length=128),
) -> dict[str, Any]:
    """Start a fresh session (new RunSpec); do not reuse cookie session_id."""
    return await _init_or_resume_session(
        agent_id,
        InitBody(session_id=None, model=model),
        request,
        db,
        redis,
        user,
        reuse_cookie=False,
    )


@router.post("/{agent_id}/chat")
async def chat(
    agent_id: str,
    body: ChatBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
    user: Annotated[UserContext, Depends(get_current_user)],
) -> StreamingResponse:
    """SSE stream for chat turn."""
    # 1. Degradation check
    deg = DegradationService()
    deg_state = await deg.get_level()
    if deg_state.level >= 5:
        raise AgentFactoryException(
            "DEGRADED_READ_ONLY",
            "系统处于只读降级模式，请稍后再试",
            status_code=503,
        )

    # 2. Load session
    q = await db.execute(
        select(ChatSession).where(ChatSession.session_id == body.session_id)
    )
    session = q.scalar_one_or_none()
    if session is None:
        raise AgentFactoryException(
            "SESSION_REQUIRED", "Session not found", status_code=401
        )
    if session.expires_at and session.expires_at < _utc_now():
        raise AgentFactoryException(
            "SESSION_EXPIRED", "Session expired", status_code=401
        )
    if session.agent_id != agent_id:
        raise AgentFactoryException(
            "FORBIDDEN", "Session agent mismatch", status_code=403
        )

    settings = get_settings()
    clean_message = strip_format_and_control_chars(
        body.message,
        max_chars=settings.CHAT_USER_MESSAGE_MAX_CHARS,
    ).strip()
    if not clean_message:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "消息无效或为空",
            status_code=400,
        )

    window = int(time.time()) // 60
    rl_key = f"rl:chat_sess:{body.session_id}:{window}"
    try:
        n = await redis.incr(rl_key)
        if n == 1:
            await redis.expire(rl_key, 70)
        if n > settings.CHAT_RATE_LIMIT_PER_SESSION_PER_MINUTE:
            raise AgentFactoryException(
                "CHAT_RATE_LIMITED",
                "请求过于频繁，请稍后再试",
                status_code=429,
            )
    except AgentFactoryException:
        raise
    except Exception:
        logger.warning("chat session rate limit check skipped (redis error)")

    # 3. Session lock (bounded wait queue — plan §12)
    ok_lock, lock_err = await acquire_session_lock_or_wait(
        redis,
        body.session_id,
        max_waiters=settings.SESSION_CHAT_LOCK_MAX_WAITERS,
        poll_interval_ms=settings.SESSION_CHAT_LOCK_POLL_MS,
        max_wait_ms=settings.SESSION_CHAT_LOCK_WAIT_MS,
    )
    if not ok_lock:
        lock_msgs: dict[str, tuple[str, int]] = {
            "SESSION_BUSY": ("当前会话正在处理中，请稍后再试", 429),
            "SESSION_QUEUE_FULL": ("排队已满，请稍后重试", 429),
            "SESSION_LOCK_TIMEOUT": ("等待回复超时，请稍后重试", 408),
        }
        msg, sc = lock_msgs.get(lock_err or "", ("当前会话繁忙", 429))
        raise AgentFactoryException(
            lock_err or "SESSION_BUSY",
            msg,
            status_code=sc,
        )

    # 4. Load RunSpec
    if not session.run_id:
        await release_session_lock(redis, body.session_id)
        raise AgentFactoryException(
            "COMPILE_ERROR", "No RunSpec for session", status_code=400
        )
    q_rs = await db.execute(
        select(RunSpec).where(RunSpec.run_id == session.run_id)
    )
    run_spec = q_rs.scalar_one_or_none()
    if run_spec is None:
        await release_session_lock(redis, body.session_id)
        raise AgentFactoryException(
            "RUNSPEC_MISMATCH", "RunSpec not found", status_code=400
        )

    rt0 = run_spec.runtime if isinstance(run_spec.runtime, dict) else {}
    est = int(rt0.get("max_tokens", 8000))
    quota_pairs = [
        ("platform", "global"),
        ("department", (user.department or "").strip()),
        ("agent", agent_id.strip()),
        ("user", user.user_id_hash),
    ]
    for scope, sid in quota_pairs:
        if scope == "department" and not sid:
            continue
        await qsvc.check_quota_allows_estimate(
            db, scope=scope, scope_id=sid, estimated_tokens=est
        )

    inj = prompt_injection_risk_score(clean_message)
    if inj >= 4 and run_spec.run_id:
        await set_audit_elevation(run_id=run_spec.run_id, level="standard")

    ex_r = await db.execute(
        select(AgentApp.degradation_exempt).where(AgentApp.id == agent_id)
    )
    degradation_exempt = bool(ex_r.scalar_one_or_none())

    lat_sig = await read_latency_ema_ms(redis)
    rate_sig, _, _ = await window_error_rate(
        window_minutes=settings.DEGRADATION_AUTO_WINDOW_MINUTES,
        redis=redis,
    )
    cc_pf, qp = await _resolve_model_queue_context(
        db,
        run_spec,
        body.file_ids or [],
    )
    lat_p99 = await read_latency_p99_ms(redis=redis)
    doc_depth = await doc_parse_queue_depth(redis)
    circ_open = await any_http_tool_circuit_open(redis)
    deg_knobs = build_degradation_run_knobs(
        latency_ema_ms=lat_sig,
        latency_p99_ms=lat_p99,
        error_rate=rate_sig,
        settings=settings,
        queue_priority=qp,
        global_level=deg_state.level,
        doc_queue_depth=doc_depth,
        http_circuit_open=circ_open,
    )
    raw_bt = run_spec.allowed_tools or []
    if isinstance(raw_bt, list):
        base_tools = [str(t).strip() for t in raw_bt if str(t).strip()]
    else:
        logger.warning(
            "run_spec.allowed_tools_not_list",
            extra={
                "run_id": run_spec.run_id,
                "agent_id": agent_id,
                "type": type(raw_bt).__name__,
            },
        )
        base_tools = []
    eff_tools = await filter_allowed_tools_under_circuit(
        db,
        redis,
        base_tools,
        agent_degradation_exempt=degradation_exempt,
        settings=settings,
    )

    try:
        await preflight_model_queue_or_raise(redis, settings, cc_pf)
    except ModelQueuePolicyError as exc:
        await release_session_lock(redis, body.session_id)
        raise HTTPException(
            status_code=exc.http_status,
            detail={
                "code": "MODEL_QUEUE_BUSY",
                "message": "模型排队繁忙，请稍后重试",
                "retry_after": exc.retry_after,
            },
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    tool_gateway = get_tool_gateway()
    if deg_state.level >= 4:
        # L4+ strips most tools; keep read-only built-ins still in RunSpec.
        allowed_tools_override = [
            t
            for t in base_tools
            if t in ("doc.extract", "read_reference")
        ]
    elif deg_knobs.strip_nonessential_tools and deg_state.level < 4:
        allowed_tools_override = eff_tools
    elif eff_tools != base_tools:
        allowed_tools_override = eff_tools
    else:
        allowed_tools_override = None

    model_gateway = get_model_gateway()
    runner = RunnerService(model_gateway, tool_gateway)
    caller_perms = effective_permissions(
        user.permissions,
        legacy_agent_admin_implies_full=settings.RBAC_LEGACY_AGENT_ADMIN_IMPLIES_FULL,
    )

    async def _event_stream() -> AsyncGenerator[str, None]:
        usage_tokens = 0
        last_out = ""
        try:
            if deg_state.level > 0:
                deg_evt = {
                    "type": "degradation",
                    "level": deg_state.level,
                    "reason": deg_state.reason,
                    "message": widget_degradation_hint(
                        deg_state.level,
                        deg_state.reason,
                    ),
                }
                yield (
                    "event: message\n"
                    f"data: {json.dumps(deg_evt, ensure_ascii=False)}\n\n"
                )
            async for event in runner.run_turn(
                db=db,
                run_spec=run_spec,
                session=session,
                user_message=clean_message,
                file_ids=body.file_ids or [],
                caller_permissions=caller_perms,
                degradation_exempt=degradation_exempt,
                allowed_tools_override=allowed_tools_override,
                degradation_knobs=deg_knobs,
            ):
                if event.get("type") == "done":
                    u = event.get("usage") or {}
                    pt = u.get("total_tokens")
                    if pt is not None:
                        try:
                            usage_tokens = int(pt)
                        except (TypeError, ValueError):
                            usage_tokens = 0
                    if not usage_tokens:
                        usage_tokens = int(u.get("prompt_tokens") or 0) + int(
                            u.get("completion_tokens") or 0
                        )
                    last_out = str(event.get("output") or "")
                data = json.dumps(event, ensure_ascii=False)
                yield f"event: message\ndata: {data}\n\n"
        except AgentFactoryException as exc:
            if exc.code == "TOKEN_QUOTA_EXCEEDED":
                err = json.dumps(
                    {
                        "type": "error",
                        "code": exc.code,
                        "message": exc.message,
                    },
                    ensure_ascii=False,
                )
                yield f"event: message\ndata: {err}\n\n"
            else:
                raise
        except Exception:
            logger.exception("Runner error")
            err = json.dumps(
                {
                    "type": "error",
                    "code": "INTERNAL_ERROR",
                    "message": "服务暂时不可用，请稍后重试",
                },
                ensure_ascii=False,
            )
            yield f"event: message\ndata: {err}\n\n"
        finally:
            if usage_tokens > 0:
                for scope, sid in quota_pairs:
                    if scope == "department" and not sid:
                        continue
                    try:
                        await qsvc.increment_used_tokens(
                            db,
                            scope=scope,
                            scope_id=sid,
                            tokens=usage_tokens,
                        )
                    except Exception:
                        logger.exception("quota increment skipped")
                try:
                    await db.commit()
                except Exception:
                    logger.exception("db commit after quota failed")
                try:
                    audit_cfg = (
                        run_spec.audit if isinstance(run_spec.audit, dict) else {}
                    )
                    base_level = str(audit_cfg.get("level") or "minimal")
                    await push_audit_event(
                        run_id=run_spec.run_id,
                        session_id=session.session_id,
                        user_id_hash=user.user_id_hash,
                        agent_id=agent_id,
                        department=user.department,
                        tool_calls=None,
                        token_count=usage_tokens,
                        error_code=None,
                        retrieval_ids=None,
                        base_audit_level=base_level,
                        prompt_summary=clean_message[:2000],
                        full_prompt=clean_message if base_level == "full" else None,
                        full_output=last_out if base_level == "full" else None,
                    )
                except Exception:
                    logger.exception("audit push skipped")
            await release_session_lock(redis, body.session_id)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/{agent_id}/resume")
async def resume_session(
    agent_id: str,
    body: ResumeBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[UserContext, Depends(get_current_user)],
) -> dict[str, Any]:
    """Resume session from checkpoint."""
    q = await db.execute(
        select(ChatSession).where(ChatSession.session_id == body.session_id)
    )
    session = q.scalar_one_or_none()
    if session is None:
        raise AgentFactoryException(
            "SESSION_EXPIRED", "Session not found", status_code=401
        )
    if session.expires_at and session.expires_at < _utc_now():
        raise AgentFactoryException(
            "SESSION_EXPIRED", "Session expired", status_code=401
        )

    if session.run_id:
        q_rs = await db.execute(
            select(RunSpec).where(RunSpec.run_id == session.run_id)
        )
        _ = q_rs.scalar_one_or_none()

    # Load latest checkpoint messages
    from agent_factory.db.models.checkpoint import Checkpoint

    messages: list[dict[str, Any]] = []
    if session.run_id:
        q_cp = await db.execute(
            select(Checkpoint)
            .where(Checkpoint.run_id == session.run_id)
            .order_by(Checkpoint.turn_number.desc())
            .limit(1)
        )
        cp = q_cp.scalar_one_or_none()
        if cp and cp.messages:
            messages = list(cp.messages)

    q_agent = await db.execute(select(AgentApp).where(AgentApp.id == agent_id))
    agent = q_agent.scalar_one_or_none()
    ui: dict[str, Any] = {}
    if agent and isinstance(agent.ui_config, dict):
        ui = agent.ui_config

    return {
        "session_id": session.session_id,
        "run_id": session.run_id,
        "status": session.status,
        "messages": messages,
        "turn_count": session.turn_count,
        "ui_config": ui,
    }


@router.post("/{agent_id}/upload")
async def upload_file(
    agent_id: str,
    request: Request,
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
    user: Annotated[UserContext, Depends(get_current_user)],
) -> dict[str, Any]:
    """Upload file; large payloads enqueue doc parser (docs/24, docs/39)."""
    # Degradation check: level >= 3 disables file uploads
    deg = DegradationService()
    deg_state = await deg.get_level()
    if deg_state.level >= 3:
        raise AgentFactoryException(
            "DEGRADED_UPLOAD_DISABLED",
            "文件上传功能暂时不可用，请稍后再试",
            status_code=503,
        )

    s = get_settings()
    sid = request.cookies.get(s.SESSION_COOKIE_NAME)
    if not sid:
        raise AgentFactoryException(
            "SESSION_REQUIRED", "Session required", status_code=401
        )

    contents = await file.read()

    q_agent = await db.execute(select(AgentApp).where(AgentApp.id == agent_id))
    agent_app = q_agent.scalar_one_or_none()
    if agent_app is None:
        raise AgentFactoryException(
            "NOT_FOUND",
            "Agent not found",
            status_code=404,
        )
    ui_cfg = agent_app.ui_config if isinstance(agent_app.ui_config, dict) else None
    ok_up, err_up = validate_upload_for_ui_config(
        filename=file.filename or "unnamed",
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(contents),
        ui_config=ui_cfg,
        content_head=contents[:MAGIC_SNIFF_BYTES],
    )
    if not ok_up:
        upload_msgs: dict[str, tuple[str, int]] = {
            "ATTACHMENTS_DISABLED": ("该 Agent 未开启附件上传", 400),
            "FILE_TOO_LARGE": ("文件超出大小限制", 400),
            "FILE_TYPE_NOT_ALLOWED": ("文件类型不允许", 400),
            "MIME_MAGIC_MISMATCH": ("文件内容与类型不一致", 400),
        }
        um, usc = upload_msgs.get(
            err_up or "",
            ("上传被拒绝", 400),
        )
        raise AgentFactoryException(err_up or "INVALID_PARAMS", um, status_code=usc)

    # P0: store to MinIO (stub if unavailable)
    try:
        minio = MinioClient(s)
        file_id = f"file_{uuid.uuid4().hex}"
        storage_path = f"temp/{sid}/{file_id}"
        await minio.put_object(
            bucket=s.MINIO_BUCKET,
            object_name=storage_path,
            data=contents,
            length=len(contents),
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception:
        logger.exception("MinIO upload failed; storing path as None")
        file_id = f"file_{uuid.uuid4().hex}"
        storage_path = None

    row = FileUpload(
        file_id=file_id,
        session_id=sid,
        user_id_hash=user.user_id_hash,
        file_name=sanitize_upload_filename(file.filename),
        file_size=len(contents),
        mime_type=file.content_type or "application/octet-stream",
        sha256=_body_sha256_hex(contents),
        storage_path=storage_path,
        status="pending",
        created_at=_utc_now(),
        expires_at=_utc_now().replace(hour=23, minute=59, second=59),
    )
    db.add(row)
    await db.flush()

    depth = await doc_parse_queue_depth(redis)
    force_async = depth >= s.DOC_PARSE_QUEUE_FORCE_ASYNC_DEPTH
    if force_async or len(contents) >= s.DOC_PARSE_ASYNC_MIN_BYTES:
        try:
            await enqueue_doc_parse_job(
                redis=redis,
                file_id=row.file_id,
                file_size=len(contents),
            )
        except Exception:
            logger.exception("enqueue_doc_parse_job failed for %s", row.file_id)

    return {
        "file_id": row.file_id,
        "name": row.file_name,
        "size": row.file_size,
    }


async def _persist_feedback(
    db: AsyncSession,
    body: FeedbackBody,
) -> dict[str, str]:
    row = FeedbackLog(
        session_id=body.session_id,
        message_id=body.message_id,
        run_id=body.run_id,
        agent_id=body.agent_id,
        feedback=body.feedback,
        reasons=body.reasons,
        comment=body.comment or None,
        timestamp=_utc_now(),
    )
    db.add(row)
    await db.flush()
    return {"status": "ok"}


@router.post("/{agent_id}/feedback")
async def post_feedback(
    agent_id: str,
    body: FeedbackBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _user: Annotated[UserContext, Depends(get_current_user)],
) -> dict[str, str]:
    """Record user feedback (path agent_id must match body)."""
    if body.agent_id != agent_id:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "agent_id in path and body must match",
            status_code=400,
        )
    return await _persist_feedback(db, body)


@router.post("/{agent_id}/tasks")
async def create_task(
    agent_id: str,
    body: TaskCreateBody,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(redis_dep)],
    user: Annotated[UserContext, Depends(get_current_user)],
) -> dict[str, Any]:
    """Create a background agent task (non-blocking)."""
    q = await db.execute(
        select(ChatSession).where(ChatSession.session_id == body.session_id)
    )
    session = q.scalar_one_or_none()
    if session is None:
        raise AgentFactoryException(
            "SESSION_REQUIRED", "Session not found", status_code=401
        )
    if session.agent_id != agent_id:
        raise AgentFactoryException(
            "FORBIDDEN", "Session agent mismatch", status_code=403
        )

    if not session.run_id:
        raise AgentFactoryException(
            "COMPILE_ERROR", "No RunSpec for session", status_code=400
        )
    q_rs = await db.execute(
        select(RunSpec).where(RunSpec.run_id == session.run_id)
    )
    run_spec = q_rs.scalar_one_or_none()
    if run_spec is None:
        raise AgentFactoryException(
            "RUNSPEC_MISMATCH", "RunSpec not found", status_code=400
        )

    from agent_factory.services.agent_task import get_task_manager

    tm = get_task_manager()
    task = tm.create(agent_id, body.session_id)

    async def _background() -> None:
        factory = get_session_factory()
        async with factory() as bg_db:
            try:
                tm.set_running(task.task_id)
                q_sess = await bg_db.execute(
                    select(ChatSession).where(
                        ChatSession.session_id == body.session_id
                    )
                )
                bg_session = q_sess.scalar_one_or_none()
                if bg_session is None:
                    tm.set_error(task.task_id, "Session disappeared")
                    return
                q_rs2 = await bg_db.execute(
                    select(RunSpec).where(RunSpec.run_id == bg_session.run_id)
                )
                bg_run_spec = q_rs2.scalar_one_or_none()
                if bg_run_spec is None:
                    tm.set_error(task.task_id, "RunSpec disappeared")
                    return
                model_gateway = get_model_gateway()
                tool_gateway = get_tool_gateway()
                runner = RunnerService(model_gateway, tool_gateway)
                caller_perms = effective_permissions(
                    user.permissions,
                    legacy_agent_admin_implies_full=get_settings().RBAC_LEGACY_AGENT_ADMIN_IMPLIES_FULL,
                )
                result = await runner.run_turn_background(
                    db=bg_db,
                    run_spec=bg_run_spec,
                    session=bg_session,
                    user_message=body.message,
                    file_ids=body.file_ids or [],
                    caller_permissions=caller_perms,
                )
                tm.set_done(task.task_id, result)
                await bg_db.commit()
            except Exception as exc:
                logger.exception("background_task_failed")
                tm.set_error(task.task_id, str(exc))
                await bg_db.rollback()

    asyncio.create_task(_background())
    return {"task_id": task.task_id, "status": task.status}


@router.get("/{agent_id}/tasks/{task_id}")
async def get_task(
    agent_id: str,
    task_id: str,
    _user: Annotated[UserContext, Depends(get_current_user_or_operator)],
) -> dict[str, Any]:
    """Query task status and result."""
    from agent_factory.services.agent_task import get_task_manager

    tm = get_task_manager()
    task = tm.get(task_id)
    if task is None or task.agent_id != agent_id:
        raise AgentFactoryException(
            "TASK_NOT_FOUND", "Task not found", status_code=404
        )
    return {
        "task_id": task.task_id,
        "agent_id": task.agent_id,
        "session_id": task.session_id,
        "status": task.status,
        "result": task.result,
        "error": task.error,
    }
