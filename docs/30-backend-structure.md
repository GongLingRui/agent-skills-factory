# 30. 后端工程结构

> 版本：v0.6 · 2026-05-06

---

## 文档定位（对照 PRD）

本后端对应 PRD **§4 总体架构**中的：**API 网关 / SSO**、**Agent App 注册中心**、**Skill Compiler**、**RunSpec**、**共享 Agent Runner**、**模型网关与队列**、**Tool Gateway**、**审计**、**文档解析 / 受控脚本 Worker（外协知识服务由网关调用）**。不落地的边界见 [prd.md](../prd.md) §2（不做 RAG 平台本体、不做 Skill Creator、P0 不做 multi-skill / 运行时脚本等）。

### PRD 模块 → 代码映射

| PRD 模块 | 主要目录 / 服务 |
|----------|----------------|
| API 网关 / SSO / 限流 | `api/v1/auth.py`、`middleware/rate_limit.py`、`middleware/cors.py` |
| Agent App 注册中心 | `services/agent_service.py`、`core/models.py`（AgentApp）、DB 表 |
| Skill Compiler | `core/compiler.py`、`services/compiler_service.py`、[07-skill-compiler.md](07-skill-compiler.md) |
| RunSpec | `core/models.py`（RunSpec）、编译产物校验 |
| Agent Runner | `core/runner.py`、`services/runner_service.py`、[08-agent-runner.md](08-agent-runner.md) |
| 模型网关 / 队列 / fallback | `services/model_gateway.py`、`config/models.yaml`、[10-model-gateway.md](10-model-gateway.md) |
| Tool Gateway | `services/tool_gateway.py`、[09-tool-gateway.md](09-tool-gateway.md) |
| Skill Registry HTTP | `api/v1/skills.py` + registry 存储 |
| Tool Registry HTTP | `api/v1/tools.py` |
| 审计（minimal 异步写入） | `services/audit_service.py`、`workers/audit_worker.py`、[12-security-audit.md](12-security-audit.md) |
| MAU 元数据（会话 init） | `services/usage_service.py` 或在 `agent_service` 内写 `agent_usage_log`（[prd.md](../prd.md) §10.5） |
| 文档解析 Worker | `workers/document_parser_worker.py`（消费者）[24-document-parser-worker.md](24-document-parser-worker.md) |
| 受控脚本 Worker（P2+） | `workers/script_worker.py`（占位）[25-script-worker.md](25-script-worker.md) |
| 文件上传 / MinIO | `services/file_service.py`、`infra/minio_client.py`、[39-file-pipeline-design.md](39-file-pipeline-design.md) |
| 消息队列（Redis Streams） | `infra/redis.py`、`workers/*`、[26-message-queue.md](26-message-queue.md) |
| 降级策略 | `services/degradation_service.py`（或 `admin` 写入全局状态 Redis）、[13-concurrency.md](13-concurrency.md) |
| 定时任务（cron / K8s CronJob） | `jobs/` 或独立进程调用 `services/*`、[21-cron-jobs.md](21-cron-jobs.md) |
| 观测 | `GET /metrics` Prometheus、`middleware/logging.py`、[32-observability-design.md](32-observability-design.md) |

---

## 项目目录结构

```
agent_factory/
├── src/
│   ├── main.py                    # FastAPI 入口：创建 app、挂载路由、启动事件
│   ├── __init__.py
│   ├── api/                       # 接口层（路由 + 依赖注入）
│   │   ├── __init__.py
│   │   ├── deps.py                # FastAPI Depends：当前用户、DB、Redis、权限校验
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py            # /auth/* 路由
│   │   │   ├── agents.py          # /agents/* 路由（用户侧 + 部分 admin 可拆）
│   │   │   ├── skills.py          # /skills/* 路由（Skill Registry）
│   │   │   ├── tools.py           # /tools/* 路由（Tool Registry）
│   │   │   ├── policies.py        # /policies/* 路由（platform / org）
│   │   │   ├── audit.py           # /audit/* 路由（查询类，P0.5+ 消费端）
│   │   │   ├── admin.py           # /admin/* 路由（降级、配额、用户等）
│   │   │   ├── feedback.py        # POST /feedback（亦可并入 agents）
│   │   │   └── metrics_frontend.py# POST /metrics/frontend（前端指标接入）
│   │   ├── health.py              # GET /health /ready（Kubernetes 探针）
│   │   └── sse.py                 # SSE 流式响应封装（chat）
│   ├── core/                      # 核心域（纯业务逻辑，无框架依赖）
│   │   ├── __init__.py
│   │   ├── models.py              # Pydantic 领域模型（AgentApp、RunSpec、Session 等）
│   │   ├── compiler.py            # Skill Compiler 纯函数
│   │   ├── runner.py              # Agent Runner 状态机
│   │   ├── permissions.py         # 权限交集计算
│   │   └── prompt_builder.py      # Prompt 拼装（按优先级）
│   ├── services/                  # 服务层（协调多个核心域 + 外部调用）
│   │   ├── __init__.py
│   │   ├── agent_service.py       # Agent 生命周期、灰度版本选择、usage_log
│   │   ├── auth_service.py        # JWT 签发/验证、session、jti 一次性
│   │   ├── compiler_service.py    # Skill Compiler 调用封装（含缓存）
│   │   ├── runner_service.py      # Agent Runner、checkpoint、SSE 泵
│   │   ├── model_gateway.py       # 模型路由、队列、fallback、token 预算扣减对接
│   │   ├── tool_gateway.py        # Tool 权限校验、熔断、路由到 kb/doc/internal
│   │   ├── audit_service.py       # 审计事件投递 Stream / 批量写 PG
│   │   ├── file_service.py        # 上传、秒传 hash、MinIO、投递 doc 队列
│   │   ├── degradation_service.py # 全局降级等级、与 13-concurrency 阈值联动
│   │   ├── usage_service.py       # agent_usage_log（MAU）、按日聚合
│   │   └── input_sanitizer.py     # 注入试探检测 → 降优先级 / 日志（见 34-p0）
│   ├── infra/                     # 基础设施（外部依赖适配器）
│   │   ├── __init__.py
│   │   ├── db.py                  # SQLAlchemy engine / session
│   │   ├── redis.py               # Redis 连接池、封装常用操作
│   │   ├── minio_client.py        # MinIO / S3 客户端
│   │   ├── jwt.py                 # PyJWT 封装
│   │   ├── model_client.py        # OpenAI 兼容 HTTP 客户端
│   │   └── sse_publisher.py       # SSE 事件推送封装
│   ├── workers/                   # 异步 Worker（独立进程或 sidecar）
│   │   ├── __init__.py
│   │   ├── audit_worker.py        # Redis Stream mq:audit → PostgreSQL
│   │   ├── checkpoint_worker.py   # checkpoint 异步落盘 / 修剪
│   │   ├── quota_worker.py        # token 预算异步汇总
│   │   ├── cleanup_worker.py      # 会话过期、temp 文件、归档任务
│   │   ├── document_parser_worker.py  # Redis Stream doc_jobs → doc.extract 结果
│   │   └── script_worker.py       # P2+ 受控脚本（P0 仅占位）
│   ├── config/                    # 配置加载
│   │   ├── __init__.py
│   │   ├── settings.py            # Pydantic-Settings：环境变量 + .yaml 配置
│   │   └── models.yaml            # 模型配置（endpoint / rpm / tpm）
│   ├── middleware/                # FastAPI 中间件
│   │   ├── __init__.py
│   │   ├── cors.py                # CORS 配置
│   │   ├── logging.py             # 请求日志（自动 mask token）
│   │   ├── error_handler.py       # 全局异常捕获 → 统一错误响应
│   │   └── rate_limit.py          # 入口限流（IP / 用户 / 全局）
│   ├── jobs/                      # 定时任务入口（CronJob 调 CLI）
│   │   └── retention_mau.py       # MAU 体检、cold 迁移（对齐 PRD §15.1）
│   └── cli/                       # 管理命令
│       ├── __init__.py
│       ├── init.py                # python -m agent_factory init（种子数据见 23-system-init）
│       └── admin.py               # python -m agent_factory admin create
├── tests/
│   ├── unit/                      # 单元测试
│   ├── integration/               # 集成测试
│   ├── e2e/                       # 端到端测试
│   └── conftest.py                # pytest fixtures（DB、Redis、MinIO mock）
├── alembic/                       # 数据库迁移
│   └── versions/
├── migrations/                    # 种子数据 SQL
├── helm/                          # K8s Helm Charts
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## 依赖注入（FastAPI Depends）

### src/api/deps.py

```python
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

# 1. 获取数据库会话
async def get_db() -> AsyncSession:
    async with async_session_maker() as session:
        yield session

# 2. 获取 Redis 连接
async def get_redis() -> Redis:
    yield redis_pool

# 3. 获取当前用户（从 session cookie 解析）
async def get_current_user(request: Request, redis: Redis = Depends(get_redis)) -> UserContext:
    session_cookie = request.cookies.get("session_id")
    if not session_cookie:
        raise HTTPException(status_code=401, detail="SESSION_REQUIRED")
    user = await auth_service.validate_session(session_cookie, redis)
    if not user:
        raise HTTPException(status_code=401, detail="SESSION_EXPIRED")
    return user

# 4. 权限校验装饰器
def require_permission(perm: str):
    def checker(user: UserContext = Depends(get_current_user)):
        if perm not in user.permissions:
            raise HTTPException(status_code=403, detail="FORBIDDEN")
        return user
    return Depends(checker)
```

### 使用方式

```python
from fastapi import APIRouter, Depends
from src.api.deps import get_db, get_redis, get_current_user, require_permission

router = APIRouter()

@router.post("/agents/{agent_id}/init")
async def init_session(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user: UserContext = Depends(get_current_user),
):
    ...

@router.post("/admin/degradation/level")
async def set_degradation(
    ...,
    _ = require_permission("degradation.control"),
):
    ...
```

---

## 中间件链

### 加载顺序（main.py）

```python
app = FastAPI(title="Agent App Factory", version="0.1.0")

# 1. CORS（最外层）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 入口限流
app.add_middleware(RateLimitMiddleware, redis_pool=redis_pool)

# 3. 安全响应头
app.add_middleware(SecurityHeadersMiddleware)

# 4. 请求日志（含自动 mask token）
app.add_middleware(LoggingMiddleware)

# 5. 全局异常捕获（最内层，确保捕获所有业务异常）
app.add_exception_handler(AgentFactoryException, agent_factory_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)
```

### 各中间件职责

| 中间件 | 职责 | 关键行为 |
|--------|------|---------|
| CORSMiddleware | 跨域控制 | `Access-Control-Allow-Origin` 严格白名单 |
| RateLimitMiddleware | 入口限流 | IP / user_id / 全局三级限流，超限返回 429 |
| SecurityHeadersMiddleware | 安全响应头 | `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff` |
| LoggingMiddleware | 请求日志 | 自动 mask URL 中的 `token` 参数；记录 trace_id |
| ErrorHandler | 异常统一响应 | 业务异常 → 结构化 JSON；未知异常 → 500 + 告警 |

---

## 异常处理基类

### src/middleware/error_handler.py

```python
from fastapi import Request
from fastapi.responses import JSONResponse

class AgentFactoryException(Exception):
    """业务异常基类"""
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code

class CompileError(AgentFactoryException):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, status_code=400)

class PermissionDenied(AgentFactoryException):
    def __init__(self, message: str):
        super().__init__("FORBIDDEN", message, status_code=403)

class AgentInactive(AgentFactoryException):
    def __init__(self, agent_id: str):
        super().__init__("AGENT_INACTIVE", f"Agent {agent_id} is inactive", status_code=403)

class RateLimitExceeded(AgentFactoryException):
    def __init__(self):
        super().__init__("RATE_LIMITED", "Rate limit exceeded", status_code=429)

# 全局异常处理器
async def agent_factory_exception_handler(request: Request, exc: AgentFactoryException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request.state.trace_id,
            }
        },
    )

async def generic_exception_handler(request: Request, exc: Exception):
    # 记录错误日志 + 告警
    logger.exception("Unhandled exception", extra={"request_id": request.state.trace_id})
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
                "request_id": request.state.trace_id,
            }
        },
    )
```

---

## 配置加载机制

### src/config/settings.py

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === 基础 ===
    APP_ENV: str = "development"           # development / staging / production
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # === 数据库 ===
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost/agent_factory"
    DATABASE_POOL_SIZE: int = 20

    # === Redis ===
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 50

    # === MinIO ===
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_BUCKET: str = "agent-factory"

    # === JWT ===
    JWT_SECRET: str = Field(..., description="Agent Factory 私钥，用于签发 short-lived JWT")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_SECONDS: int = 300        # 5 分钟

    # === Portal JWT ===
    PORTAL_JWT_PUBLIC_KEY: str = ""      # JWKS 或 PEM 公钥，用于验证 portal-JWT

    # === Cookie ===
    SESSION_COOKIE_NAME: str = "session_id"
    SESSION_COOKIE_MAX_AGE: int = 1800   # 30 分钟
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "Strict"

    # === 限流 ===
    RATE_LIMIT_IP: int = 100             # IP 级每分钟请求数
    RATE_LIMIT_USER: int = 60            # 用户级每分钟请求数
    RATE_LIMIT_GLOBAL: int = 1000        # 全局每分钟请求数

    # === 审计 ===
    AUDIT_DEFAULT_LEVEL: str = "minimal"
    AUDIT_DEFAULT_RETAIN_DAYS: int = 90

    # === CORS ===
    ALLOWED_ORIGINS: List[str] = ["https://agent.company.com"]

    # === 模型配置路径 ===
    MODELS_CONFIG_PATH: str = "src/config/models.yaml"

settings = Settings()
```

### 配置加载优先级

```
1. 环境变量（最高优先级，覆盖所有）
2. .env 文件（开发/测试环境）
3. K8s ConfigMap / Secret（生产环境）
4. 代码默认值（最低优先级）
```

**生产环境敏感信息**：`JWT_SECRET`、`DATABASE_URL`、`MINIO_SECRET_KEY` 等全部通过 K8s Secret 注入，不写入镜像、不提交到 Git。

---

## 模型配置加载

### src/config/models.yaml

```yaml
models:
  qwen3-32b:
    provider: local
    endpoint: http://qwen3-32b.internal:8000/v1
    max_tokens: 32768
    rpm: 100
    tpm: 100000
    health_endpoint: http://qwen3-32b.internal:8000/health

  qwen3-14b:
    provider: local
    endpoint: http://qwen3-14b.internal:8000/v1
    max_tokens: 32768
    rpm: 200
    tpm: 200000
    health_endpoint: http://qwen3-14b.internal:8000/health

  qwen3-8b:
    provider: local
    endpoint: http://qwen3-8b.internal:8000/v1
    max_tokens: 32768
    rpm: 500
    tpm: 500000
    health_endpoint: http://qwen3-8b.internal:8000/health

  bge-m3:
    provider: local
    endpoint: http://bge-m3.internal:8000/v1
    type: embedding
    batch_size: 32
```

### 运行时加载

```python
# src/services/model_gateway.py
import yaml
from pathlib import Path
from src.config.settings import settings

class ModelConfigLoader:
    def __init__(self):
        self.models = {}
        self._load()

    def _load(self):
        path = Path(settings.MODELS_CONFIG_PATH)
        if not path.exists():
            raise FileNotFoundError(f"Models config not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.models = data.get("models", {})

    def get(self, model_id: str) -> dict:
        return self.models.get(model_id)

model_config = ModelConfigLoader()
```

---

## 数据库连接管理

### src/infra/db.py

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.config.settings import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=10,
    pool_pre_ping=True,               # 自动检测断线并重连
    echo=settings.DEBUG,              # DEBUG 模式打印 SQL
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
```

---

## Redis 连接管理

### src/infra/redis.py

```python
from redis.asyncio import Redis
from src.config.settings import settings

redis_pool = Redis.from_url(
    settings.REDIS_URL,
    max_connections=settings.REDIS_POOL_SIZE,
    decode_responses=True,
)
```

---

## 审计异步写入

### src/services/audit_service.py

```python
from redis.asyncio import Redis
import json

async def emit_audit_log(redis: Redis, log: dict):
    """将审计日志投递到 Redis Stream，由 Audit Worker 异步消费写入 PostgreSQL"""
    await redis.xadd("mq:audit", {
        "payload": json.dumps(log),
        "timestamp": str(time.time()),
    }, maxlen=200000)
```

**为什么异步**：审计写入是高频低优先级操作，同步写入会拖慢 API 响应。Redis Stream 保证至少一次投递，Audit Worker 批量写入 PostgreSQL。

---

## main.py 路由挂载约定

```python
# 伪代码：顺序体现中间件与路由分层
app = FastAPI(...)
register_middleware(app)           # CORS → 限流 → SecurityHeaders → Logging
app.include_router(health_router, prefix="")   # /health /ready 无前缀
app.include_router(metrics_router)               # /metrics Prometheus
app.include_router(api_v1_router, prefix="/api/v1")
```

- **`/api/v1`**：对外契约（与 [19-api-reference.md](19-api-reference.md) 一致）。
- **`/health`/`/ready`**：对齐 K8s，**不**走业务鉴权。
- **`/metrics`**：Prometheus scrape，内网 ACL / NetworkPolicy 隔离。

---

## 健康检查与观测端点

| 路径 | 用途 |
|------|------|
| `GET /health` | 进程存活（轻量） |
| `GET /ready` | PG / Redis / MinIO / 模型网关探测通过后才返回 200 |
| `GET /metrics` | `prometheus-fastapi-instrumentator` + 业务自定义 Counter/Histogram |

详见 [32-observability-design.md](32-observability-design.md)、[37-production-checklist.md](37-production-checklist.md)。

---

## 请求生命周期（对照 PRD §8）

```
HTTP → 网关中间件（限流 / 日志 mask token）
     → 认证依赖（session 或 admin JWT）
     → agents.init：加载 agent.yaml → Compiler → RunSpec → 写 session/run → usage_log
     → agents.chat：Runner 循环 → Model Gateway → Tool Gateway → SSE 写出
     → 异步：emit_audit_log、checkpoint、quota 投递 Redis Stream
```

Tool Gateway **每次**工具调用做实时权限与策略校验（PRD §7.5「RunSpec 不变 ≠ 权限不变」）。

---

## 并发等级与降级（PRD §9）

- `agent.yaml` 中 `concurrency.class`（interactive / document / batch / privileged）进入 RunSpec / 队列优先级。
- **降级服务**维护全局等级 0~6，供 Runner（模型路由）、Tool Gateway（关工具）、前端 Banner 消费。
- 阈值与恢复条件见 [13-concurrency.md](13-concurrency.md)，与 PRD §9.5 一致。

---

## Skill / Agent 物料存储

| 物料 | 存储 | 说明 |
|------|------|------|
| agent.yaml 与各版本 | PostgreSQL + Git/对象存储可选 | 注册中心保留最近 10 版本（PRD §11.5） |
| Skill 包 tarball | 对象存储 + DB 元数据 | Skill Registry（PRD §8.5），**保留全部历史版本** |
| RunSpec 快照 | 审计库 / 会话表 | 可复现 |
| 上传文件 | MinIO `temp/` | [39-file-pipeline-design.md](39-file-pipeline-design.md) |

---

## 跨边界调用（不入库代码，须在适配层实现）

| 外部系统 | 适配位置 | PRD 依据 |
|----------|----------|----------|
| 知识检索 `kb.search` | Tool Gateway → 内网知识服务 HTTP | §4 RAG 外协 |
| `doc.extract` | Tool Gateway → 文档解析 Worker / 队列结果 | §9 文档解析池 |
| 内部 OA/ERP API | Tool Gateway P1+ 逐个接入 | §8 |

---

## 相关文档索引

| 主题 | 文档 |
|------|------|
| RunSpec / Compiler | [05-runspec.md](05-runspec.md)、[07-skill-compiler.md](07-skill-compiler.md) |
| Runner / SSE | [08-agent-runner.md](08-agent-runner.md) |
| Tool / Model | [09-tool-gateway.md](09-tool-gateway.md)、[10-model-gateway.md](10-model-gateway.md) |
| 数据模型 | [17-data-models.md](17-data-models.md) |
| 队列 | [26-message-queue.md](26-message-queue.md) |
| 配置 | [31-configuration-reference.md](31-configuration-reference.md) |
| PRD 口径 | [47-prd-alignment.md](47-prd-alignment.md) |
