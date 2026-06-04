"""Cron scheduler: background tasks (docs/21, docs/34).

P0: minimal scheduler using asyncio.sleep loops.
Production: replace with APScheduler or K8s CronJob.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from agent_factory.config import get_settings
from agent_factory.workers.degradation_auto import run_degradation_auto_tick
from agent_factory.workers.retention_mau import run_mau_retention_gate

logger = logging.getLogger(__name__)

INTERVAL_SESSION_CLEANUP_SECONDS = 3600
INTERVAL_MAU_CHECK_SECONDS = 86400
INTERVAL_DEGRADATION_AUTO_SECONDS = 60
INTERVAL_AGENT_CRON_SECONDS = 30


async def _run_agent_cron_jobs() -> None:
    """Execute due agent_cron_jobs (OpenClaw cron parity)."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, pool_size=2, max_overflow=0)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )  # type: ignore[call-overload]
    try:
        from agent_factory.services.agent_cron_executor import run_due_cron_jobs

        async with async_session() as db:
            async with db.begin():
                count = await run_due_cron_jobs(db)
                if count:
                    logger.info("Executed %s agent cron jobs", count)
    except Exception:
        logger.exception("Agent cron tick failed")
    finally:
        await engine.dispose()


async def _cleanup_expired_sessions() -> None:
    """Delete expired sessions older than 7 days."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, pool_size=2, max_overflow=0)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )  # type: ignore[call-overload]

    try:
        async with async_session() as db:
            async with db.begin():
                result = await db.execute(
                    text(
                        "DELETE FROM sessions WHERE expires_at < "
                        "NOW() - INTERVAL '7 days'"
                    )
                )
                logger.info("Cleaned up %s expired sessions", result.rowcount)
    except Exception:
        logger.exception("Session cleanup failed")
    finally:
        await engine.dispose()


async def _mau_health_check() -> None:
    """Retention gate + log today's distinct user hashes (MAU proxy)."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, pool_size=2, max_overflow=0)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )  # type: ignore[call-overload]

    try:
        async with async_session() as db:
            async with db.begin():
                await run_mau_retention_gate(db, settings)
        async with async_session() as db:
            async with db.begin():
                result = await db.execute(
                    text(
                        "SELECT COUNT(DISTINCT user_id_hash) "
                        "FROM agent_usage_logs WHERE date = CURRENT_DATE"
                    )
                )
                mau = result.scalar() or 0
                logger.info("Daily MAU (distinct user_id_hash today): %s", mau)
    except Exception:
        logger.exception("MAU check failed")
    finally:
        await engine.dispose()


async def run_cron_scheduler(
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Run periodic background tasks."""
    logger.info("Cron scheduler started")

    next_cleanup = datetime.now(UTC).timestamp()
    next_mau = datetime.now(UTC).timestamp()
    next_degrade = datetime.now(UTC).timestamp()
    next_agent_cron = datetime.now(UTC).timestamp()

    try:
        while shutdown_event is None or not shutdown_event.is_set():
            now = datetime.now(UTC).timestamp()

            if now >= next_cleanup:
                await _cleanup_expired_sessions()
                next_cleanup = now + INTERVAL_SESSION_CLEANUP_SECONDS

            if now >= next_mau:
                await _mau_health_check()
                next_mau = now + INTERVAL_MAU_CHECK_SECONDS

            if now >= next_degrade:
                await run_degradation_auto_tick()
                next_degrade = now + INTERVAL_DEGRADATION_AUTO_SECONDS

            if now >= next_agent_cron:
                await _run_agent_cron_jobs()
                next_agent_cron = now + INTERVAL_AGENT_CRON_SECONDS

            await asyncio.sleep(10)
    except Exception:
        logger.exception("Cron scheduler error")
    finally:
        logger.info("Cron scheduler stopped")
