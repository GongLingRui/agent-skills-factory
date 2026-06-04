#!/usr/bin/env bash
# 一键：拉起 Compose 依赖栈、安装后端依赖、执行迁移与系统种子。
# 用法：在仓库根目录执行  ./scripts/bootstrap-dev.sh
# 可选：COMPOSE_FILE=docker-compose.yml ./scripts/bootstrap-dev.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.dev.yml}"

if ! command -v docker >/dev/null 2>&1; then
  echo "需要已安装的 Docker / Docker Compose。"
  exit 1
fi

echo "==> 启动依赖栈: $COMPOSE_FILE"
set +e
docker compose -f "$COMPOSE_FILE" up -d --wait
wait_rc=$?
set -e
if [[ "$wait_rc" -ne 0 ]]; then
  docker compose -f "$COMPOSE_FILE" up -d
  echo "==> 等待 PostgreSQL (localhost:55432)..."
  for _ in $(seq 1 60); do
    if command -v nc >/dev/null 2>&1 && nc -z localhost 55432 2>/dev/null; then
      break
    fi
    sleep 1
  done
fi

cd "$ROOT/backend"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> 已创建 backend/.env（请按需修改 DATABASE_URL 等）。"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "需要 uv：https://github.com/astral-sh/uv"
  exit 1
fi

echo "==> 后端依赖 (uv sync)"
uv sync --extra dev

echo "==> Alembic upgrade"
uv run alembic upgrade head

echo "==> 系统种子 (roles / tools 等)"
uv run python scripts/init_db.py

echo ""
echo "完成。下一步："
echo "  后端  cd backend && uv run uvicorn agent_factory.main:app --reload --host 0.0.0.0 --port 8000"
echo "  前端  cd frontend && pnpm dev"
