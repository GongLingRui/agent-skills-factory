# Agent Factory — 后端

## 依赖安装（国内镜像）

### pip

在 `backend/` 目录下：

```bash
export PIP_CONFIG_FILE="$(pwd)/pip.conf"
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip setuptools wheel
pip install -e ".[dev]"
```

不设置 `PIP_CONFIG_FILE` 时，也可单次指定索引：

```bash
pip install -e ".[dev]" \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --trusted-host pypi.tuna.tsinghua.edu.cn
```

### uv

`pyproject.toml` 已配置 `[[tool.uv.index]]` 指向清华源，直接：

```bash
cd backend
uv sync --extra dev
```

若要改用阿里云等，可修改 `pyproject.toml` 中 `url`，例如：
`https://mirrors.aliyun.com/pypi/simple/`（`uv` 同样需要 `trusted` 时见 uv 文档）。

## 数据库迁移

需先启动仓库根目录下 `docker compose up -d`（PostgreSQL / Redis / MinIO）。

**方式 A（推荐，在 `backend/` 下执行）**

```bash
cd backend
export PIP_CONFIG_FILE="$(pwd)/pip.conf"   # 若用 pip 且未全局配置镜像
uv run alembic upgrade head
# 或已 pip install -e ".[dev]"：alembic upgrade head
```

**方式 B（在仓库根目录执行）**

根目录已提供 `alembic.ini`，`script_location` 指向 `backend/alembic`。请先 `cd` 到仓库根，并设置与 backend 一致的数据库环境变量（例如复制 `backend/.env` 或在根目录创建 `.env` 含 `DATABASE_URL`），然后：

```bash
cd /path/to/agent-factory
export DATABASE_URL=postgresql+asyncpg://agent:agent@localhost:55432/agent_factory
uv run --directory backend alembic upgrade head
# 若全局已安装 alembic：alembic upgrade head
```

## 运行 API

```bash
cd backend
uvicorn agent_factory.main:app --reload --host 0.0.0.0 --port 8000
```

工作目录应为 `backend/`，且 `PYTHONPATH` 包含 `src`（可编辑安装 `-e .` 后无需单独设置）。

## CI（GitHub Actions）

`.github/workflows/ci.yml`：Job **backend** 拉起 PostgreSQL / Redis 服务容器 → `uv run alembic upgrade head` → `ruff` → `pytest`（含迁移后 `demo-agent` / `policy-qa-agent` / `contract-review-agent` 断言）；Job **frontend**：`pnpm test` + `pnpm build`。

本地一键（等价于 CI 后端静态部分）：`uv run python scripts/verify_p0.py`。

## 认证联调（portal → widget）

1. 配置 `.env`：`JWT_SECRET`、`PORTAL_JWT_SECRET`（与 portal 签发 portal-JWT 的密钥一致，HS256）、`SESSION_COOKIE_SECURE=false`（本地 HTTP）。
2. `alembic upgrade head` 后存在 `demo-agent` 种子。
3. 用 portal 同密钥签发 JWT，`sub` 为用户 ID，可选 `department`、`allowed_agents`（列表，缺省则仅校验 Agent 存在且 active）。

```bash
# 示例：Python 生成 portal-JWT 后换短令牌
curl -sS -X POST http://127.0.0.1:8000/api/v1/auth/exchange \
  -H "Authorization: Bearer <portal-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"demo-agent"}' | jq .

curl -sS -c cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/session \
  -H "Content-Type: application/json" \
  -d '{"token":"<上一步 token>"}' | jq .

curl -sS -b cookies.txt http://127.0.0.1:8000/api/v1/agents | jq .
```
