"""Alembic environment (sync psycopg3 for migrations)."""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.exc import OperationalError

# Repo layout: backend/alembic/env.py -> backend/src on path
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agent_factory.config import get_settings  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def get_url() -> str:
    return get_settings().database_url_sync


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _migration_db_unreachable_message(url: str) -> str:
    """Human hint when Postgres is down (common dev: port 55432 from compose)."""
    return (
        "\n"
        "============================================================\n"
        "Alembic 无法连接 PostgreSQL（Connection refused）\n"
        "------------------------------------------------------------\n"
        f"当前 DATABASE_URL（脱敏仅显示驱动与主机）: {_safe_db_hint(url)}\n"
        "\n"
        "请任选其一：\n"
        "  1) 启动本仓库依赖栈（需 Docker Desktop 已运行）：\n"
        "       cd <仓库根目录> && docker compose up -d postgres\n"
        "     默认会把 Postgres 映射到本机 55432（见根目录 docker-compose.yml）。\n"
        "  2) 若你本机已有 Postgres，在 backend/.env 或仓库根 .env 里设置\n"
        "       DATABASE_URL=postgresql+asyncpg://用户:密码@主机:端口/库名\n"
        "     再执行 alembic upgrade head。\n"
        "============================================================\n"
    )


def _safe_db_hint(url: str) -> str:
    if "@" in url:
        head, _, tail = url.partition("@")
        scheme = head.split("://", 1)[0] if "://" in head else head
        return f"{scheme}://***@{tail}"
    return url[:80] + ("…" if len(url) > 80 else "")


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    url = get_url()
    configuration["sqlalchemy.url"] = url
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        connection = connectable.connect()
    except OperationalError as exc:
        sys.stderr.write(_migration_db_unreachable_message(url))
        raise SystemExit(1) from exc

    with connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
