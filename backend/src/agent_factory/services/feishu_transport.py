"""Feishu event transport: WebSocket long connection or webhook."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

from agent_factory.config import Settings, get_settings
from agent_factory.infra.db import get_session_factory
from agent_factory.infra.redis import get_redis
from agent_factory.services.feishu_events import parse_im_message_event
from agent_factory.services.feishu_service import FeishuChannelService

logger = logging.getLogger(__name__)

_ws_thread: threading.Thread | None = None
_main_loop: asyncio.AbstractEventLoop | None = None
_channel: Any | None = None


async def _dispatch_inbound(msg: Any) -> None:
    """Handle normalized message from lark_oapi.channel or raw dict."""
    settings = get_settings()
    logger.info(
        "feishu_inbound_received chat_id=%s msg_type=%s",
        getattr(msg, "chat_id", None) if hasattr(msg, "chat_id") else "dict",
        type(msg).__name__,
    )
    if hasattr(msg, "message_id") and hasattr(msg, "content_text"):
        text = str(getattr(msg, "content_text", "") or "").strip()
        if not text:
            logger.info("feishu_inbound_ignored_empty_text")
            return
        from agent_factory.services.feishu_events import FeishuInboundMessage

        inbound = FeishuInboundMessage(
            message_id=str(getattr(msg, "message_id", "")),
            chat_id=str(getattr(msg, "chat_id", "")),
            chat_type=str(getattr(msg, "chat_type", "p2p")),
            sender_open_id=str(getattr(msg, "sender_id", "unknown")),
            text=text,
            mentioned_bot=bool(getattr(msg, "mentioned_bot", False)),
            raw={},
        )
    elif hasattr(msg, "message_id"):
        inbound = parse_im_message_event(
            {
                "header": {"event_type": "im.message.receive_v1"},
                "event": {
                    "sender": {
                        "sender_id": {"open_id": getattr(msg, "sender_id", "")},
                    },
                    "message": {
                        "message_id": getattr(msg, "message_id", ""),
                        "chat_id": getattr(msg, "chat_id", ""),
                        "chat_type": getattr(msg, "chat_type", "p2p"),
                        "message_type": getattr(msg, "raw_content_type", "text"),
                        "content": json.dumps(
                            {"text": getattr(msg, "content_text", "")},
                            ensure_ascii=False,
                        ),
                        "mentions": getattr(msg, "mentions", None),
                    },
                },
            },
        )
        if inbound is None:
            return
    elif isinstance(msg, dict):
        inbound = parse_im_message_event(msg)
        if inbound is None:
            return
    else:
        return

    factory = get_session_factory()
    redis = get_redis()
    async with factory() as db:
        try:
            svc = FeishuChannelService(settings)
            await svc.process_message(db, redis, inbound)
        except Exception:
            logger.exception("feishu_process_message_failed")
            await db.rollback()
            try:
                await FeishuChannelService(settings).client.send_to_chat(
                    chat_id=inbound.chat_id,
                    text="抱歉，处理消息时出错，请稍后重试。",
                    reply_message_id=inbound.message_id,
                )
            except Exception:
                logger.exception("feishu_error_reply_failed")


def _schedule_dispatch_on_main_loop(msg: Any) -> None:
    """Bridge Feishu SDK thread -> FastAPI uvicorn event loop."""
    main = _main_loop
    if main is None or not main.is_running():
        logger.error("feishu_main_loop_unavailable")
        return
    fut = asyncio.run_coroutine_threadsafe(_dispatch_inbound(msg), main)

    def _log_err(done: asyncio.Future[object]) -> None:
        exc = done.exception()
        if exc is not None:
            logger.error("feishu_dispatch_failed: %s", exc)

    fut.add_done_callback(_log_err)


def _normalize_feishu_transport(mode: str) -> str:
    """Map settings value to lark_oapi FeishuChannel transport id."""
    m = (mode or "ws").strip().lower()
    if m in {"ws", "websocket", "long", "long_connection"}:
        return "ws"
    if m == "webhook":
        return "webhook"
    raise ValueError(f"FEISHU_CONNECTION_MODE must be ws or webhook, got {mode!r}")


def _patch_lark_ws_loop(loop: asyncio.AbstractEventLoop) -> None:
    """lark_oapi.ws.client captures loop at import time; patch before start()."""
    import lark_oapi.ws.client as ws_client

    ws_client.loop = loop


def _build_feishu_channel(settings: Settings) -> Any:
    from lark_oapi.channel import FeishuChannel, PolicyConfig

    transport = _normalize_feishu_transport(settings.FEISHU_CONNECTION_MODE)
    domain = settings.FEISHU_DOMAIN.strip()
    if domain.startswith("http://") or domain.startswith("https://"):
        domain_arg = domain.rstrip("/")
    elif domain.lower() == "lark":
        domain_arg = "https://open.larksuite.com"
    else:
        domain_arg = None

    dm_policy = "open" if settings.FEISHU_DM_POLICY.strip().lower() == "open" else "disabled"
    policy = PolicyConfig(
        dm_policy=dm_policy,
        group_policy="open",
        require_mention=settings.FEISHU_GROUP_REQUIRE_MENTION,
    )

    channel = FeishuChannel(
        app_id=settings.FEISHU_APP_ID.strip(),
        app_secret=settings.FEISHU_APP_SECRET.strip(),
        verification_token=(settings.FEISHU_VERIFICATION_TOKEN or "").strip() or None,
        encrypt_key=(settings.FEISHU_ENCRYPT_KEY or "").strip() or None,
        domain=domain_arg,
        transport=transport,
        policy=policy,
    )

    def _on_message(msg: Any) -> None:
        logger.info(
            "feishu_handler_invoked chat_id=%s mentioned_bot=%s",
            getattr(msg, "chat_id", None),
            getattr(msg, "mentioned_bot", None),
        )
        _schedule_dispatch_on_main_loop(msg)

    def _on_reject(event: Any) -> None:
        logger.info(
            "feishu_sdk_rejected message_id=%s reason=%s",
            getattr(event, "message_id", None),
            getattr(event, "reason", None),
        )

    channel.on("message", _on_message)
    channel.on("reject", _on_reject)
    return channel


def _feishu_ws_thread_main(settings: Settings) -> None:
    """Run FeishuChannel.start() on an isolated asyncio loop (uvicorn-safe)."""
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _patch_lark_ws_loop(loop)

    global _channel
    try:
        _channel = _build_feishu_channel(settings)
        logger.info("feishu_websocket_thread_starting")
        _channel.start()
    except Exception:
        logger.exception("feishu_websocket_thread_failed")
    finally:
        try:
            loop.close()
        except Exception:
            pass


async def start_feishu_transport() -> None:
    """Start Feishu background transport when enabled."""
    global _ws_thread, _main_loop, _channel
    settings = get_settings()
    if not settings.FEISHU_ENABLED:
        return
    if not settings.FEISHU_APP_ID.strip() or not settings.FEISHU_APP_SECRET.strip():
        logger.warning("feishu_enabled_but_missing_credentials")
        return

    try:
        import lark_oapi  # noqa: F401
    except ImportError:
        logger.error(
            "feishu_requires_lark_oapi: pip install lark-oapi or uv add lark-oapi"
        )
        return

    _main_loop = asyncio.get_running_loop()
    mode = _normalize_feishu_transport(settings.FEISHU_CONNECTION_MODE)

    if mode == "webhook":
        _channel = _build_feishu_channel(settings)
        logger.info("feishu_webhook_mode_ready")
        return

    if _ws_thread is not None and _ws_thread.is_alive():
        logger.info("feishu_websocket_thread_already_running")
        return

    _ws_thread = threading.Thread(
        target=_feishu_ws_thread_main,
        args=(settings,),
        name="feishu-ws",
        daemon=True,
    )
    _ws_thread.start()
    logger.info("feishu_websocket_thread_started transport=ws")


async def stop_feishu_transport() -> None:
    global _ws_thread, _channel
    if _channel is not None:
        stop_fn = getattr(_channel, "stop", None)
        if callable(stop_fn):
            try:
                stop_fn()
            except Exception:
                logger.exception("feishu_stop_failed")
        _channel = None
    if _ws_thread is not None:
        _ws_thread.join(timeout=8.0)
        _ws_thread = None


async def handle_feishu_webhook_request(
    headers: dict[str, str],
    body: bytes,
) -> dict[str, Any]:
    """Webhook entry for Feishu event subscription."""
    settings = get_settings()
    try:
        from lark_oapi.channel import FeishuChannel  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("lark-oapi is required for Feishu webhook") from exc

    global _channel, _main_loop
    if _main_loop is None:
        _main_loop = asyncio.get_running_loop()
    if _channel is None:
        _channel = _build_feishu_channel(settings)

    handler = getattr(_channel, "handle_webhook_request", None)
    if callable(handler):
        result = handler(headers, body)
        if asyncio.iscoroutine(result):
            return await result
        return result if isinstance(result, dict) else {"ok": True}

    payload = json.loads(body.decode("utf-8"))
    from agent_factory.services.feishu_service import process_feishu_event_payload

    factory = get_session_factory()
    redis = get_redis()
    async with factory() as db:
        out = await process_feishu_event_payload(
            payload,
            db=db,
            redis=redis,
            settings=settings,
        )
    return out if out is not None else {"ok": True}
