"""Feishu channel: session binding, agent routing, and chat execution."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.config import Settings, get_settings
from agent_factory.core.user_context import UserContext
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.db.models.chat_session import ChatSession
from agent_factory.db.models.run_spec import RunSpec
from agent_factory.infra.session_lock import (
    acquire_session_lock_or_wait,
    release_session_lock,
)
from agent_factory.services.auth_service import hash_user_id
from agent_factory.services.compiler_service import CompilerService
from agent_factory.services.factory import get_model_gateway
from agent_factory.services.feishu_client import FeishuClient, split_feishu_text
from agent_factory.services.feishu_events import FeishuInboundMessage
from agent_factory.services.router_service import route_to_agent
from agent_factory.services.runner_service import RunnerService
from agent_factory.services.tool_gateway import ToolGateway

logger = logging.getLogger(__name__)

_SWITCH_CMD = re.compile(r"^/(?:agent|切换|switch)\s+(\S+)", re.I)
_LIST_CMD = re.compile(r"^/(?:agents|列表|list)\s*$", re.I)
_HELP_CMD = re.compile(r"^/(?:help|帮助)\s*$", re.I)
_AGENTS_TO_FEISHU_DOC = re.compile(
    r"(?:agents?|agent\s*列表).{0,48}(?:飞书|云文档|文档)"
    r"|(?:飞书|云文档|文档).{0,48}(?:agents?|agent\s*列表)",
    re.I | re.DOTALL,
)


FEISHU_EFFECTIVE_MAX_TURNS_CAP = 64


def feishu_max_turns_for_runtime(settings: Settings, runtime: dict[str, Any] | None) -> int:
    """Resolve per-message tool loop cap for Feishu (0 setting => generous cap)."""
    configured = settings.FEISHU_MAX_TURNS
    if configured <= 0:
        return FEISHU_EFFECTIVE_MAX_TURNS_CAP
    base = int((runtime or {}).get("max_turns", 6))
    return max(base, configured)


def format_feishu_run_reply(output: str, errors: list[dict[str, Any]]) -> str:
    """User-facing reply; avoid scary JSON / 'open new session' for Feishu."""
    body = (output or "").strip()
    max_turns_err = next(
        (e for e in errors if e.get("code") == "MAX_TURNS_REACHED"),
        None,
    )
    if max_turns_err:
        if body:
            return (
                f"{body}\n\n---\n\n"
                "以上是第一阶段的进展。本条任务步骤较多，**无需开新会话**，"
                "在同一个飞书对话里直接回复「继续」我接着做即可。"
            )
        return (
            "本条消息里的步骤比较多，这一轮还没全部跑完。\n\n"
            "**同一个飞书对话可以一直聊**（会记住近期上下文），"
            "你不需要重新开对话，直接再发「继续」或把任务拆小一点就行。"
        )
    if errors and not body:
        first = errors[0]
        msg = str(first.get("message") or first.get("code") or "未知错误")
        return f"处理时遇到问题：{msg}"
    return body or "（无回复内容）"


def _feishu_channel_tool_ids(settings: Settings, base: list[str]) -> list[str]:
    return list(dict.fromkeys([*(base or []), *settings.feishu_channel_extra_tools]))


def _build_feishu_user_message(msg: FeishuInboundMessage) -> str:
    """Inject Feishu runtime hints so the model uses feishu.doc / agent.list."""
    body = msg.text.strip()
    return (
        "[飞书通道上下文]\n"
        f"- 当前用户 open_id: {msg.sender_open_id}\n"
        "- 可用能力：feishu.doc（创建/读写飞书云文档，支持 Markdown）、"
        "agent.list（列出平台 Agent）\n"
        "- 用户要求写入飞书文档时，必须调用 feishu.doc（create/write/append），"
        "不要声称没有飞书文档权限\n"
        "- create 会自动授予当前用户文档编辑权限\n\n"
        f"用户消息：\n{body}"
    )


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _conv_redis_key(msg: FeishuInboundMessage) -> str:
    scope = "group" if msg.chat_type in {"group", "topic_group"} else "p2p"
    return f"feishu:conv:{scope}:{msg.chat_id}:{msg.sender_open_id}"


def _dedup_redis_key(message_id: str) -> str:
    return f"feishu:dedup:{message_id}"


def _feishu_user_hash(open_id: str, settings: Settings) -> str:
    return hash_user_id(f"feishu:{open_id}", settings.USER_ID_HASH_SALT)


def _build_user_context(
    *,
    session_id: str,
    open_id: str,
    settings: Settings,
) -> UserContext:
    return UserContext(
        session_id=session_id,
        user_id_hash=_feishu_user_hash(open_id, settings),
        department=settings.FEISHU_DEPARTMENT,
        permissions=("agent.read", "agent.write"),
        allowed_agents=None,
        data_domains=None,
    )


class FeishuChannelService:
    """Bridge Feishu messages to Agent Factory sessions and skills."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: FeishuClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or FeishuClient(self.settings)

    def should_accept(self, msg: FeishuInboundMessage) -> bool:
        if msg.chat_type in {"group", "topic_group"}:
            if self.settings.FEISHU_GROUP_REQUIRE_MENTION and not msg.mentioned_bot:
                return False
            return True
        if msg.chat_type == "p2p":
            return self.settings.FEISHU_DM_POLICY.strip().lower() != "disabled"
        return True

    async def list_candidate_agent_ids(self, db: AsyncSession) -> list[str]:
        configured = self.settings.feishu_candidate_agent_ids
        if configured:
            return configured
        q = await db.execute(
            select(AgentApp.id).where(AgentApp.lifecycle_state == "active")
        )
        return [str(row[0]) for row in q.all()][:32]

    async def resolve_agent_id(
        self,
        db: AsyncSession,
        *,
        user_message: str,
        current_agent_id: str | None,
    ) -> tuple[str, dict[str, Any] | None]:
        settings = self.settings
        default = (settings.FEISHU_DEFAULT_AGENT_ID or "").strip()
        candidates = await self.list_candidate_agent_ids(db)
        if not candidates:
            raise RuntimeError("No active agents available for Feishu routing")

        switch = _SWITCH_CMD.match(user_message.strip())
        if switch:
            aid = switch.group(1).strip()
            if aid in candidates:
                return aid, {"router": "command", "agent_id": aid}
            return (
                current_agent_id or default or candidates[0],
                {"router": "command_invalid", "requested": aid},
            )

        sticky = (current_agent_id or "").strip()
        if sticky and sticky in candidates and not settings.FEISHU_ROUTE_EACH_TURN:
            return sticky, None

        if default and default in candidates and len(candidates) == 1:
            return default, {"router": "default_only"}

        gateway = get_model_gateway()
        route = await route_to_agent(
            db,
            user_message=user_message,
            candidate_agent_ids=candidates,
            department=settings.FEISHU_DEPARTMENT,
            model_gateway=gateway,
            require_api_feature=False,
            prefer_llm=settings.FEISHU_ROUTER_USE_LLM,
        )
        aid = str(route.get("agent_id") or "").strip()
        if not aid:
            aid = default or candidates[0]
        return aid, route

    async def get_or_create_session(
        self,
        db: AsyncSession,
        redis: Redis,
        msg: FeishuInboundMessage,
        *,
        agent_id: str,
    ) -> ChatSession:
        key = _conv_redis_key(msg)
        cached = await redis.get(key)
        if cached:
            sid = cached.decode() if isinstance(cached, bytes) else str(cached)
            q = await db.execute(
                select(ChatSession).where(ChatSession.session_id == sid)
            )
            row = q.scalar_one_or_none()
            if row is not None:
                row.last_activity = _utc_now()
                if row.agent_id != agent_id:
                    row.agent_id = agent_id
                    row.run_id = None
                return row

        sid = f"sess_feishu_{uuid.uuid4().hex}"
        user_ctx = _build_user_context(
            session_id=sid,
            open_id=msg.sender_open_id,
            settings=self.settings,
        )
        compiler = CompilerService(self.settings)
        run_spec = await compiler.compile_and_save(
            db=db,
            agent_id=agent_id,
            user_ctx=user_ctx,
        )

        now = _utc_now()
        expires = now + timedelta(days=self.settings.FEISHU_SESSION_TTL_DAYS)
        row = ChatSession(
            session_id=sid,
            run_id=run_spec.run_id,
            user_id_hash=user_ctx.user_id_hash,
            agent_id=agent_id,
            department=self.settings.FEISHU_DEPARTMENT,
            status="running",
            turn_count=0,
            total_tokens=0,
            created_at=now,
            last_activity=now,
            expires_at=expires,
            allowed_agents=None,
            permissions=list(user_ctx.permissions),
            revoke_gen_seen=0,
            runtime_context={
                "channel": "feishu",
                "feishu_chat_id": msg.chat_id,
                "feishu_chat_type": msg.chat_type,
                "feishu_open_id": msg.sender_open_id,
            },
            session_kind="main",
            label=f"feishu:{msg.chat_type}:{msg.chat_id}",
        )
        db.add(row)
        await db.flush()
        await redis.set(key, sid, ex=60 * 60 * 24 * self.settings.FEISHU_SESSION_TTL_DAYS)
        return row

    async def _ensure_runspec(
        self,
        db: AsyncSession,
        session: ChatSession,
        *,
        agent_id: str,
        open_id: str,
    ) -> RunSpec:
        if session.run_id and session.agent_id == agent_id:
            q = await db.execute(
                select(RunSpec).where(RunSpec.run_id == session.run_id)
            )
            rs = q.scalar_one_or_none()
            if rs is not None:
                return rs

        user_ctx = _build_user_context(
            session_id=session.session_id,
            open_id=open_id,
            settings=self.settings,
        )
        compiler = CompilerService(self.settings)
        run_spec = await compiler.compile_and_save(
            db=db,
            agent_id=agent_id,
            user_ctx=user_ctx,
        )
        session.run_id = run_spec.run_id
        session.agent_id = agent_id
        session.status = "running"
        await db.flush()
        return run_spec

    async def handle_command_shortcuts(
        self,
        db: AsyncSession,
        msg: FeishuInboundMessage,
    ) -> str | None:
        text = msg.text.strip()
        if _HELP_CMD.match(text):
            candidates = await self.list_candidate_agent_ids(db)
            lines = [
                "Agent Factory 飞书助手",
                "",
                "直接描述需求，我会自动选择合适的业务 Agent（Skill）。",
                "",
                "**会话说明**：同一个飞书群/私聊会持续记住上下文（默认 "
                f"{self.settings.FEISHU_SESSION_TTL_DAYS} 天），可以一直往下聊，"
                "不用每次开新对话。",
                "",
                "命令：",
                "  /agents — 列出可用 Agent",
                "  /agent <id> — 切换到指定 Agent",
                "",
                f"当前候选 Agent（{len(candidates)}）：",
            ]
            q = await db.execute(
                select(AgentApp).where(AgentApp.id.in_(candidates))
            )
            for ag in q.scalars().all():
                lines.append(f"  • {ag.id} — {ag.name or ag.id}")
            return "\n".join(lines)

        if _LIST_CMD.match(text):
            candidates = await self.list_candidate_agent_ids(db)
            q = await db.execute(
                select(AgentApp).where(AgentApp.id.in_(candidates))
            )
            rows = list(q.scalars().all())
            if not rows:
                return "暂无可用 Agent，请在平台注册并启用。"
            lines = ["可用 Agent："]
            for ag in rows:
                lines.append(f"- {ag.id}: {ag.name or ag.id}")
            return "\n".join(lines)

        switch = _SWITCH_CMD.match(text)
        if switch and switch.group(1) not in await self.list_candidate_agent_ids(db):
            bad = switch.group(1)
            return f"未找到 Agent `{bad}`，发送 /agents 查看列表。"
        return None

    async def try_export_agents_to_feishu_doc(
        self,
        db: AsyncSession,
        msg: FeishuInboundMessage,
    ) -> str | None:
        if not _AGENTS_TO_FEISHU_DOC.search(msg.text.strip()):
            return None
        from agent_factory.services.feishu_doc_tools import export_agents_to_feishu_document

        try:
            result = await export_agents_to_feishu_document(
                db,
                requester_open_id=msg.sender_open_id,
                settings=self.settings,
            )
        except Exception as exc:
            logger.exception("feishu_export_agents_doc_failed")
            return f"导出 Agent 列表到飞书文档失败：{exc}"

        url = str(result.get("url") or "")
        count = result.get("agent_count", 0)
        title = str(result.get("title") or "Agent Factory 可用 Agents")
        return (
            f"已将 **{count}** 个可用 Agent 写入飞书文档《{title}》。\n\n"
            f"链接：{url}\n\n"
            "（已自动授予你编辑权限，可直接打开修改。）"
        )

    async def process_message(
        self,
        db: AsyncSession,
        redis: Redis,
        msg: FeishuInboundMessage,
    ) -> None:
        if not self.should_accept(msg):
            logger.info(
                "feishu_message_ignored chat_type=%s mentioned_bot=%s",
                msg.chat_type,
                msg.mentioned_bot,
            )
            if (
                msg.chat_type in {"group", "topic_group"}
                and self.settings.FEISHU_GROUP_REQUIRE_MENTION
                and not msg.mentioned_bot
            ):
                await self._reply_chunks(
                    msg,
                    "群聊里请先 @机器人 再提问；私聊可直接发送消息。",
                )
                await db.commit()
            return

        try:
            await self.client.send_to_chat(
                chat_id=msg.chat_id,
                text="收到，正在处理…",
                reply_message_id=msg.message_id,
                reply_format="text",
            )
        except Exception:
            logger.exception("feishu_ack_failed")

        dedup_key = _dedup_redis_key(msg.message_id)
        if not await redis.set(dedup_key, "1", nx=True, ex=600):
            logger.info("feishu_duplicate_message", extra={"message_id": msg.message_id})
            return

        shortcut = await self.handle_command_shortcuts(db, msg)
        if shortcut is not None and not _SWITCH_CMD.match(msg.text.strip()):
            await self._reply_chunks(msg, shortcut)
            await db.commit()
            return

        agents_doc = await self.try_export_agents_to_feishu_doc(db, msg)
        if agents_doc is not None:
            await self._reply_chunks(msg, agents_doc)
            await db.commit()
            return

        switch_match = _SWITCH_CMD.match(msg.text.strip())
        if switch_match:
            requested = switch_match.group(1).strip()
            candidates = await self.list_candidate_agent_ids(db)
            if requested not in candidates:
                await self._reply_chunks(
                    msg,
                    f"未找到 Agent `{requested}`，发送 /agents 查看列表。",
                )
                await db.commit()
                return
            session = await self.get_or_create_session(
                db, redis, msg, agent_id=requested
            )
            await self._ensure_runspec(
                db,
                session,
                agent_id=requested,
                open_id=msg.sender_open_id,
            )
            q = await db.execute(
                select(AgentApp).where(AgentApp.id == requested)
            )
            ag = q.scalar_one_or_none()
            label = ag.name if ag and ag.name else requested
            await self._reply_chunks(msg, f"已切换到 **{label}**（`{requested}`）。")
            await db.commit()
            return

        key = _conv_redis_key(msg)
        cached_sid = await redis.get(key)
        current_agent: str | None = None
        if cached_sid:
            sid = cached_sid.decode() if isinstance(cached_sid, bytes) else str(cached_sid)
            q = await db.execute(
                select(ChatSession).where(ChatSession.session_id == sid)
            )
            sess = q.scalar_one_or_none()
            if sess is not None:
                current_agent = sess.agent_id

        agent_id, route_meta = await self.resolve_agent_id(
            db,
            user_message=msg.text,
            current_agent_id=current_agent,
        )
        session = await self.get_or_create_session(
            db, redis, msg, agent_id=agent_id
        )
        run_spec = await self._ensure_runspec(
            db,
            session,
            agent_id=agent_id,
            open_id=msg.sender_open_id,
        )
        runtime = dict(run_spec.runtime or {})
        runtime["max_turns"] = feishu_max_turns_for_runtime(self.settings, runtime)
        run_spec.runtime = runtime
        await db.flush()

        ok_lock, lock_err = await acquire_session_lock_or_wait(
            redis,
            session.session_id,
            max_waiters=self.settings.SESSION_CHAT_LOCK_MAX_WAITERS,
            poll_interval_ms=self.settings.SESSION_CHAT_LOCK_POLL_MS,
            max_wait_ms=self.settings.SESSION_CHAT_LOCK_WAIT_MS,
        )
        if not ok_lock:
            await self._reply_chunks(
                msg,
                "当前会话正在处理上一条消息，请稍后再试。",
            )
            await db.commit()
            return

        try:
            runner = RunnerService(get_model_gateway(), ToolGateway())
            user_ctx = _build_user_context(
                session_id=session.session_id,
                open_id=msg.sender_open_id,
                settings=self.settings,
            )
            prefix = ""
            if route_meta and route_meta.get("router") not in {
                None,
                "command",
                "command_invalid",
            }:
                reason = str(route_meta.get("reason") or "").strip()
                if reason:
                    prefix = f"[已路由至 {agent_id}：{reason}]\n\n"

            result = await runner.run_turn_background(
                db=db,
                run_spec=run_spec,
                session=session,
                user_message=_build_feishu_user_message(msg),
                caller_permissions=frozenset(user_ctx.permissions),
                allowed_tools_override=_feishu_channel_tool_ids(
                    self.settings,
                    list(run_spec.allowed_tools or []),
                ),
                degradation_exempt=True,
            )
            errors = result.get("errors") or []
            reply = prefix + format_feishu_run_reply(
                str(result.get("output") or ""),
                errors if isinstance(errors, list) else [],
            )
            session.last_activity = _utc_now()
            session.run_status = (
                "done"
                if not errors or str(result.get("output") or "").strip()
                else "failed"
            )
            await db.flush()
            await self._reply_chunks(msg, reply)
            await db.commit()
        finally:
            await release_session_lock(redis, session.session_id)

    async def _reply_chunks(
        self,
        msg: FeishuInboundMessage,
        text: str,
    ) -> None:
        chunks = split_feishu_text(text, self.settings.FEISHU_REPLY_MAX_CHARS)
        for i, chunk in enumerate(chunks):
            suffix = f"\n\n（{i + 1}/{len(chunks)}）" if len(chunks) > 1 else ""
            body = chunk + suffix
            await self.client.send_to_chat(
                chat_id=msg.chat_id,
                text=body,
                reply_message_id=msg.message_id if i == 0 else None,
                reply_format=(
                    "markdown"
                    if self.settings.FEISHU_REPLY_USE_MARKDOWN
                    else "text"
                ),
            )


async def process_feishu_event_payload(
    payload: dict[str, Any],
    *,
    db: AsyncSession,
    redis: Redis,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Handle raw Feishu webhook/WS event; return HTTP body for URL verification."""
    from agent_factory.services.feishu_events import (
        parse_im_message_event,
        url_verification_challenge,
    )

    challenge = url_verification_challenge(payload)
    if challenge is not None:
        return {"challenge": challenge}

    msg = parse_im_message_event(payload)
    if msg is None:
        return None

    svc = FeishuChannelService(settings)
    await svc.process_message(db, redis, msg)
    return None
