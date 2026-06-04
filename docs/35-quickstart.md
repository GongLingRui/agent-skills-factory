# 35. 开发快速启动指南

> 版本：v0.6 · 2026-05-06

---

## 环境准备

### 必需依赖

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 后端运行时 |
| Node.js | 20+ | 前端构建 |
| PostgreSQL | 15+ | 主数据库 |
| Redis | 7+ | 缓存 / 队列 / Session |
| MinIO | 最新稳定版 | 对象存储 |

### 开发工具

```bash
# 后端（在 backend/ 下，推荐 uv）
cd backend
uv sync --extra dev
# 或：pip install -e ".[dev]"

# 前端
cd frontend
pnpm install

# 预提交钩子（可选）
pre-commit install
```

---

## 一键启动开发环境

### 方式 A：脚本（推荐）

在仓库根目录（需已安装 Docker、`uv`）：

```bash
./scripts/bootstrap-dev.sh
```

等价于：Compose 拉起 PostgreSQL / Redis / MinIO → `uv sync` → `alembic upgrade head` → `init_db.py`。

### 方式 B：分步

#### 1. 基础设施（Docker Compose）

在仓库根目录：

```bash
docker compose -f docker-compose.dev.yml up -d
# 或：docker compose -f docker-compose.yml up -d
# 启动：PostgreSQL（映射主机 55432）、Redis（56379）、MinIO（59000）
```

#### 2. 数据库迁移与种子

```bash
cd backend
cp .env.example .env   # 按需改 DATABASE_URL 等
uv run alembic upgrade head
# 推荐：uv run python scripts/init_db.py   # 角色 / Tool / 策略等系统种子
```

### 3. 启动后端

```bash
cd backend
uv run uvicorn agent_factory.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 启动前端

```bash
cd frontend
pnpm dev
# 默认 http://localhost:5173
```

#### 本地免 portal 打开 Widget（推荐）

仓库已包含 `frontend/.env.development`（`VITE_DEV_WIDGET_AUTH_BYPASS=true`）与 `backend/.env.example` 中的 `DEV_WIDGET_AUTH_BYPASS=true`。将后端示例复制为 `backend/.env` 后，确保其中 **`APP_ENV=development`** 且 **`DEV_WIDGET_AUTH_BYPASS=true`**，则浏览器直接访问：

`http://localhost:5173/apps/demo-agent`

即可建立会话与 `init`（**勿在生产环境**开启 `DEV_WIDGET_AUTH_BYPASS`）。

若聊天 SSE 出现 **`MODEL_UNAVAILABLE` / `HTTP 502`**：多为 `models.yaml` 指向的供应商或本地推理地址不可达。本地可设 **`MODEL_DEV_MOCK=true`**（与 `APP_ENV=development` 同时，见 `backend/.env.example`），则不走外呼模型接口，仅返回占位文本便于联调 UI。

---

## 验证环境

```bash
# 健康检查
curl http://localhost:8000/health

# 列出预设 Tool（需匿名或按部署开启；本地可调 auth 策略）
curl http://localhost:8000/api/v1/tools
```

管理员 / RBAC 种子见 `backend/scripts/init_db.py` 与迁移；生产权限模型以运维导入为准。

---

## 开发工作流

### 新增 Agent

1. 在 `agents/` 下创建目录（如 `my-agent/`）
2. 编写 `agent.yaml`（参考 [03-agent-app-spec.md](03-agent-app-spec.md)）
3. 准备 Skill 包（或复用已有 Skill）
4. 通过管理后台注册 Agent，或调用 `POST /api/v1/agents`

### 新增 Skill

1. 在独立仓库准备 Skill 包（`SKILL.md` + `enterprise.yaml` + 配套文件）
2. 确保 `evals/` 下有用例且通过
3. 调用 `POST /api/v1/skills` 上传

### 调试 RunSpec 编译

通过 `POST /api/v1/agents/{agent_id}/init`（需登录会话）触发编译并拿到 `run_id`；或编写小型脚本调用 `CompilerService`（见 `backend/src/agent_factory/services/compiler_service.py`）。

---

## 测试

```bash
cd backend
uv run pytest tests/unit -q
# 集成 / DB 冒烟（需 PostgreSQL 与迁移）：uv run pytest tests/integration -q
# P0 门禁（ruff + 全量 pytest）：uv run python scripts/verify_p0.py
```

---

## 常用端口

| 服务 | 端口 | 说明 |
|------|------|------|
| API Gateway | 8000 | FastAPI 开发服务器 |
| Widget Vite | 5173 | 前端开发服务器 |
| PostgreSQL | **55432**（主机 → 容器 5432） | 默认见根目录 `docker-compose.yml` |
| Redis | **56379**（主机 → 6379） | 同上 |
| MinIO API | **59000**（主机 → 9000） | 同上 |
| MinIO Console | **59001** | 同上 |

本地连接串示例：`postgresql+asyncpg://agent:agent@localhost:55432/agent_factory`（与 `backend/.env.example` 一致）。

---

## 相关文档

- 完整技术栈 → [15-tech-stack.md](15-tech-stack.md)
- 后端工程结构 → [30-backend-structure.md](30-backend-structure.md)
- 前端工程结构 → [29-frontend-structure.md](29-frontend-structure.md)
- 测试策略 → [27-testing-strategy.md](27-testing-strategy.md)
