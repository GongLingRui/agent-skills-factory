"""Startup dependency probes with actionable dev hints."""

from __future__ import annotations

import logging

from agent_factory.config import Settings
from agent_factory.services.readiness import (
    check_postgres,
    check_redis,
    run_all_readiness,
)

logger = logging.getLogger(__name__)

_DEV_HINT = (
    "本地依赖未就绪：请先启动 Docker Desktop，然后在仓库根目录执行 "
    "`docker compose up -d postgres redis minio`"
)


def dependency_unavailable_message(settings: Settings) -> str:
    url = settings.DATABASE_URL
    host = "localhost:55432"
    if "@" in url:
        host = url.split("@", 1)[-1].split("/", 1)[0]
    return (
        f"无法连接 PostgreSQL（{host}）。{_DEV_HINT}"
        if settings.APP_ENV == "development"
        else "数据库暂不可用，请稍后重试或联系运维。"
    )


def is_connection_refused_error(exc: BaseException) -> bool:
    if isinstance(exc, BaseExceptionGroup):
        return any(is_connection_refused_error(e) for e in exc.exceptions)

    cur: BaseException | None = exc
    while cur is not None:
        if isinstance(cur, ConnectionRefusedError):
            return True
        if isinstance(cur, OSError) and getattr(cur, "errno", None) == 61:
            return True
        if "connection refused" in str(cur).lower():
            return True
        cur = cur.__cause__ or cur.__context__
    return False


async def log_startup_dependency_status(settings: Settings) -> bool:
    """Probe core deps at boot; return True when PostgreSQL + Redis are up."""
    from agent_factory.infra.db import get_session_factory

    factory = get_session_factory()
    all_ok = True
    async with factory() as db:
        pg = await check_postgres(db)
        if not pg.ok:
            all_ok = False
            logger.error("startup_check_postgresql_failed detail=%s", pg.detail)
        else:
            logger.info("startup_check_postgresql_ok")

    rd = await check_redis(settings.REDIS_URL)
    if not rd.ok:
        all_ok = False
        logger.error("startup_check_redis_failed detail=%s", rd.detail)
    else:
        logger.info("startup_check_redis_ok")

    if not all_ok and settings.APP_ENV == "development":
        logger.error("startup_dependency_hint %s", _DEV_HINT)

    return all_ok


async def summarize_readiness_for_dev(settings: Settings) -> dict[str, object]:
    from agent_factory.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        probes = await run_all_readiness(settings, db)
    failed = [p for p in probes if not p.ok]
    return {
        "ok": not failed,
        "checks": {p.name: {"ok": p.ok, "detail": p.detail} for p in probes},
        "hint": None if not failed else _DEV_HINT,
    }
