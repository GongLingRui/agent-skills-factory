# 31. 配置文件总览

> 版本：v0.6 · 2026-05-06

---

## 配置文件清单

| 配置文件 | 格式 | 部署方式 | 敏感信息 | 热加载 |
|----------|------|---------|---------|--------|
| `.env` / `.env.local` | key=value | 本地开发 | 是（本地假密钥） | 否（重启生效） |
| `src/config/models.yaml` | YAML | 代码仓库 / ConfigMap | 否 | 否（重启生效） |
| `platform_policies` | DB 表 | 初始化 SQL + 管理后台 | 否 | 是（缓存 TTL 1min） |
| `org_policies` | DB 表 | 管理后台 | 否 | 是（缓存 TTL 1min） |
| `system_config` | DB 表 | 初始化 SQL + 管理后台 | 否 | 是（缓存 TTL 5min） |
| `agent.yaml` | YAML + DB | DB 主存储 + 对象存储备份 | 否 | 是（缓存 TTL 5min） |
| K8s ConfigMap | YAML | K8s | 否 | 否（重启 Pod 生效） |
| K8s Secret | base64 | K8s | **是**（生产密钥） | 否（重启 Pod 生效） |
| 外部 KMS / Vault | API | 生产环境 | **是** | 否 |

---

## 环境变量完整清单

### 基础配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `APP_ENV` | `development` | 运行环境：development / staging / production |
| `DEBUG` | `False` | DEBUG 模式（打印 SQL、详细错误堆栈） |
| `LOG_LEVEL` | `INFO` | 日志级别：DEBUG / INFO / WARNING / ERROR |

### 数据库

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | 主库连接串（异步驱动） |
| `DATABASE_POOL_SIZE` | `20` | 连接池大小 |

### Redis

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |
| `REDIS_POOL_SIZE` | `50` | 连接池大小 |

### MinIO / S3

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MINIO_ENDPOINT` | `localhost:9000` | 对象存储地址 |
| `MINIO_ACCESS_KEY` | - | Access Key |
| `MINIO_SECRET_KEY` | - | Secret Key（K8s Secret 注入） |
| `MINIO_BUCKET` | `agent-factory` | 默认桶名 |

### JWT

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `JWT_SECRET` | - | Agent Factory 私钥（**必须设置**） |
| `JWT_ALGORITHM` | `HS256` | 签名算法 |
| `JWT_EXPIRE_SECONDS` | `300` | short-lived JWT 过期时间（秒） |
| `PORTAL_JWT_PUBLIC_KEY` | - | Portal 公钥（JWKS URL 或 PEM） |

### Cookie / Session

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SESSION_COOKIE_NAME` | `session_id` | Cookie 名称 |
| `SESSION_COOKIE_MAX_AGE` | `1800` | 有效期（秒），默认 30 分钟 |
| `SESSION_COOKIE_SECURE` | `True` | 仅 HTTPS 传输 |
| `SESSION_COOKIE_SAMESITE` | `Strict` | SameSite 策略 |

### 限流

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `RATE_LIMIT_IP` | `100` | 单 IP 每分钟请求数 |
| `RATE_LIMIT_USER` | `60` | 单用户每分钟请求数 |
| `RATE_LIMIT_GLOBAL` | `1000` | 全平台每分钟请求数 |

### 审计

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `AUDIT_DEFAULT_LEVEL` | `minimal` | 默认审计档位 |
| `AUDIT_DEFAULT_RETAIN_DAYS` | `90` | 默认保留天数 |

### CORS

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ALLOWED_ORIGINS` | `https://agent.company.com` | 允许的跨域来源（逗号分隔），**必须包含 portal 域名** |

### 模型配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MODELS_CONFIG_PATH` | `src/config/models.yaml` | 模型配置文件路径 |
| `MINIMAX_API_KEY` | 空 | 写入 `models.yaml` 中 `MiniMax-M2.7` 的 `api_key`；**国内密钥** 与默认 endpoint `https://api.minimaxi.com/v1` 配套，**国际密钥** 见 [10-model-gateway.md](10-model-gateway.md)。 |

### Tool Gateway（Registry `http_api`）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `INTERNAL_HTTP_TOOL_URL_PREFIXES` | 空 | 逗号分隔的 **URL 前缀白名单**；`tools` 表中 `implementation.type=http_api` 的端点必须匹配其一；**为空则禁用**此类动态调用（内置 `kb.search` 等不受影响）。 |
| `INTERNAL_HTTP_TOOL_BEARER_TOKEN` | 空 | 可选；设置时对出站请求附加 `Authorization: Bearer …`。 |

**HTTP 出站熔断（Redis）**：对上游 **5xx** 与 **传输失败** 计数；**4xx** 不计入。可按工具在 `tools.rate_limit` JSON 中设置 `circuit_breaker` 覆盖阈值（见代码 `infra/tool_circuit_breaker.py`）。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `TOOL_HTTP_CIRCUIT_ENABLED` | `true` | 总开关；`false` 时关闭熔断逻辑。 |
| `TOOL_HTTP_CIRCUIT_FAILURE_THRESHOLD` | `5` | 窗口内失败次数达到该值则打开熔断。 |
| `TOOL_HTTP_CIRCUIT_WINDOW_SECONDS` | `60` | 失败计数窗口（秒）。 |
| `TOOL_HTTP_CIRCUIT_OPEN_SECONDS` | `30` | 熔断打开后拒绝请求的持续时间（秒）。 |
| `TOOL_HTTP_CIRCUIT_PER_DEPARTMENT` | `true` | 为 `true` 且会话带 `department` 时，熔断 scope 按工具 + 部门隔离。 |

### Runner（`POST .../chat` 会话锁）

有界等待同会话的后续请求（Redis），避免仅返回 429。详见 `plan.md` §12。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SESSION_CHAT_LOCK_MAX_WAITERS` | `8` | 同会话最多并发等待数；`0` 表示不等待（立即 `SESSION_BUSY`）。 |
| `SESSION_CHAT_LOCK_WAIT_MS` | `45000` | 等待锁的最长时间（毫秒）。 |
| `SESSION_CHAT_LOCK_POLL_MS` | `150` | 轮询间隔（毫秒）。 |

### 模型网关多队列（docs/10）

每类 Redis key `model:zqueue:{class}` **ZSET**：score = `-queue_priority×1e15 + 时间(ms)`（**更小**更优先；同优先级 **FIFO**）。仅当 ticket 为 **队首**且 `model:inflight:{class}` 未达 cap 时 Lua 原子 **ZREM + INCR**。`queue_priority` 来自 `run_spec.runtime.queue_priority`（1–10）或类默认（privileged=10…batch=1）；`agent_apps.degradation_exempt` 时强制 **privileged + 10**。`ModelGateway.chat(..., concurrency_class=..., queue_priority=...)`。实现：`infra/model_queue.py`。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MODEL_QUEUE_ENABLED` | `true` | `false` 时跳过队列（便于本地开发）。 |
| `MODEL_QUEUE_CAP_PRIVILEGED` | `32` | 每类最大 **并行** HTTP 流（inflight，0=不限制）。 |
| `MODEL_QUEUE_CAP_INTERACTIVE` | `64` | 同上。 |
| `MODEL_QUEUE_CAP_DOCUMENT` | `24` | 同上。 |
| `MODEL_QUEUE_CAP_BATCH` | `16` | 同上。 |
| `MODEL_QUEUE_MAX_ZQUEUE_PRIVILEGED` | `100` | 单类 ZSET **等待**条数上限（`ZCARD` 超限拒收）。 |
| `MODEL_QUEUE_MAX_ZQUEUE_INTERACTIVE` | `1000` | 同上。 |
| `MODEL_QUEUE_MAX_ZQUEUE_DOCUMENT` | `500` | 同上。 |
| `MODEL_QUEUE_MAX_ZQUEUE_BATCH` | `2000` | 同上。 |
| `MODEL_QUEUE_CAP_EMBEDDING` | `32` | 每批 HTTP embedding 的 **inflight** 上限（与批合并配合）。 |
| `MODEL_QUEUE_ACQUIRE_TIMEOUT_MS` | `120000` | 等待队首+槽位的上限（毫秒）。 |
| `MODEL_QUEUE_POLL_MS` | `50` | 轮询间隔（毫秒）。 |
| `MODEL_QUEUE_SOFT_ZCARD_INTERACTIVE` | `900` | `ZCARD` 软上限；HTTP 预检超限时 **429** + `Retry-After`（秒）。 |
| `MODEL_QUEUE_SOFT_ZCARD_DOCUMENT` | `450` | 同上（document 类）。 |
| `MODEL_QUEUE_SOFT_ZCARD_PRIVILEGED` | `98` | 同上（privileged 类）。 |
| `MODEL_QUEUE_RETRY_AFTER_INTERACTIVE` | `5` | interactive 类 `Retry-After` 秒数。 |
| `MODEL_QUEUE_RETRY_AFTER_DOCUMENT` | `30` | document 类。 |
| `MODEL_QUEUE_RETRY_AFTER_PRIVILEGED` | `10` | privileged 类。 |
| `MODEL_QUEUE_AGING_SEC_1` | `30` | 等待达该秒数后第一次 **ZINCRBY** 降分（优先级老化）。 |
| `MODEL_QUEUE_AGING_SEC_2` | `60` | 第二次老化阈值。 |
| `MODEL_QUEUE_AGING_SEC_3` | `120` | 第三次老化阈值。 |
| `MODEL_QUEUE_AGING_DELTA_1` | `1e14` | 第一次老化的 score 增量（负向 boost）。 |
| `MODEL_QUEUE_AGING_DELTA_2` | `1e14` | 第二次。 |
| `MODEL_QUEUE_AGING_FORCE_DELTA` | `5e15` | 第三次（强 boost，近「强制」前移）。 |

公平与容量：`document`/`batch` 非空时 Lua 对 `interactive`/`privileged` 维持 **5:1** 出队比（Redis `model:fair:credits`）。`batch` 在 `ZCARD ≥ max` 时对队首侧 **ZPOPMIN** 丢弃最老等待并 nack；`privileged` 满时 **ZPOPMAX** 驱逐 `interactive` 队尾。

#### Embedding 批合并（`kb.search` 异步路径）

`infra/embedding_batch.py`：`EMBEDDING_BATCH_WINDOW_MS`（默认 **100**）内合并多条查询，一次 `POST …/embeddings`（`input` 为数组）；未配置 `EMBEDDING_ENDPOINT` 时使用 **SHA256 伪向量**（32 维）便于无上游开发。批请求前后包在 `acquire_embedding_queue_slot` 内。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `EMBEDDING_ENDPOINT` | `""` | OpenAI 兼容 embeddings **根** URL（如 `https://api.openai.com/v1`）；空=伪向量。 |
| `EMBEDDING_API_KEY` | `""` | `Authorization: Bearer`。 |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | 上游 `model` 字段。 |
| `EMBEDDING_BATCH_WINDOW_MS` | `100` | 合并窗口（毫秒）。 |
| `EMBEDDING_BATCH_MAX_ITEMS` | `64` | 单批最大条数。 |
| `EMBEDDING_HTTP_TIMEOUT_SECONDS` | `60` | 单批 HTTP 超时。 |

### 降级自动恢复（docs/13）

`cron_scheduler` 约每 **60s** 调用 `workers/degradation_auto.py`：根据 `infra/model_runtime_signals.py` 写入 Redis 的分钟桶 `mw:att:*` / `mw:fail:*` 与延迟 EMA `mw:lat_ema_ms` 做**升一级**或**连续良好 streak 后降一级**。运维 `POST /admin/degradation/level`（非 0）会写 `global:degradation:operator_hold`，自动逻辑**跳过**直至 `level` 回到 `0`（与 `POST /admin/degradation/recover` 一致清除 hold）。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DEGRADATION_AUTO_ENABLED` | `false` | `true` 时启用自动升降级（生产前需调阈值）。 |
| `DEGRADATION_AUTO_WINDOW_MINUTES` | `3` | 统计失败率时向前看的分钟桶个数。 |
| `DEGRADATION_AUTO_ESCALATE_ERROR_RATE` | `0.12` | 窗口失败率 ≥ 该值则升一级（上限 5）。 |
| `DEGRADATION_AUTO_RECOVER_MAX_ERROR_RATE` | `0.02` | 低于该值且延迟 EMA 低于恢复阈值、且尝试次数 ≥ `DEGRADATION_AUTO_MIN_ATTEMPTS_FOR_RECOVER` 时累计「良好 streak」。 |
| `DEGRADATION_AUTO_GOOD_STREAK_SECONDS` | `300` | 良好指标连续保持该秒数后自动 **降一级**。 |
| `DEGRADATION_AUTO_LATENCY_ESCALATE_MS` | `45000` | 延迟 EMA（毫秒）超过则参与「升一级」判断。 |
| `DEGRADATION_AUTO_LATENCY_RECOVER_MS` | `8000` | 延迟 EMA 低于该值才允许进入恢复路径。 |
| `DEGRADATION_AUTO_MIN_ATTEMPTS_FOR_RECOVER` | `8` | 窗口内总尝试次数低于该值不自动降级（防冷启动误触发）。 |

### MAU 体检与 Agent 生命周期（retention gate）

与 [docs/21-cron-jobs.md](21-cron-jobs.md)、`workers/retention_mau.py`、`cron_scheduler` 夜间任务对齐；`agent_apps.enterprise_config.mau_threshold` 可覆盖默认阈值。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MAU_RETENTION_GATE_ENABLED` | `false` | `true` 时夜间任务按窗口统计 MAU，低于阈值将 `lifecycle_state` 标为 `cold`，超期 `cold` 可标 `archived`。开发环境默认关闭，避免无流量种子被误标。 |
| `MAU_RETENTION_WINDOW_DAYS` | `30` | 统计窗口（天）。 |
| `MAU_RETENTION_DEFAULT_THRESHOLD` | `5` | 窗口内 `distinct user_id_hash` 低于该值 → cold（可按 Agent 覆盖）。 |
| `MAU_COLD_ARCHIVE_AFTER_DAYS` | `90` | 处于 `cold` 超过该天数 → `archived`。 |

### Widget 会话展示（Auth）

| API / 行为 | 说明 |
|-------------|------|
| `GET /api/v1/auth/me` | 返回 `user_id_hint`、`department`（脱敏），供 Chat Widget 顶栏展示；需 HttpOnly `session_id` Cookie。详见 [19-api-reference.md](19-api-reference.md)。 |

### RunSpec schema 版本（Runner）

当前 Runner 仅实现 **v1 执行语义**。`run_specs.runspec_schema_version > 1` 时仍按 v1 跑，并在日志中 `INFO` 记录（便于审计回放与后续 v2 开发）；完整多版本 Runner 见 `plan.md` §13.2。

### 文档解析（上传 ≥ 阈值投递异步队列）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DOC_PARSE_ASYNC_MIN_BYTES` | `10485760`（10MiB） | 上传字节数 ≥ 该值时向 Redis Stream `mq:doc_jobs` 投递解析任务（与 [24-document-parser-worker.md](24-document-parser-worker.md) 对齐）。 |

### Skill Registry（入库评测门禁）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SKILL_EVAL_GATE_LIVE` | `false` | `true` 且 `package_metadata.eval_cases` 非空时实调模型打分。 |
| `SKILL_EVAL_GATE_MODEL` | 空 | 覆盖评测所用模型；空则使用 `models.yaml` 的 `defaults.model`。 |
| `SKILL_EVAL_GATE_RPM` | `0` | 评测门禁每分钟调用上限（Redis）；`0` 表示沿用该模型在 `models.yaml` 中的 `rpm`。 |

### 本地 Widget 免 portal（仅开发）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DEV_WIDGET_AUTH_BYPASS` | `false` | **`APP_ENV=development` 且为 `true`** 时，`POST /api/v1/auth/dev/session` 可为浏览器写入会话 Cookie（免门户 JWT）。须与前端 `VITE_DEV_WIDGET_AUTH_BYPASS=true`（见 `frontend/.env.development`）同时启用。**生产必须关闭。** |
| `MODEL_DEV_MOCK` | `false` | **`APP_ENV=development` 且为 `true`** 时，对话不请求外部模型 HTTP，由 `ModelGateway` 返回固定 MOCK 流（避免 MiniMax/本地 vLLM 不通时的 **502 / MODEL_UNAVAILABLE**）。上线须 `false`。 |

### OpenTelemetry（可选 traces）

安装：`uv sync --extra observability`。未安装时勿将 `OTEL_ENABLED` 设为 `true`，否则启动日志会提示缺少依赖。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `OTEL_ENABLED` | `false` | `true` 时向 OTLP/HTTP 导出 trace（需可选依赖与 endpoint）。 |
| `OTEL_SERVICE_NAME` | `agent-factory-api` | `service.name` 资源属性。 |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | 空 | OTLP/HTTP traces URL，例如 `http://localhost:4318/v1/traces`。为空则跳过导出配置。 |
| `OTEL_TRACES_SAMPLER_RATIO` | `1.0` | 根 span 采样率 `0.0`–`1.0`（`TraceIdRatioBased`）。 |

### 管理 / 审计查询 API

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ADMIN_API_TOKEN` | 空 | `Bearer` 令牌；用于 `/api/v1/admin/*`、部分运维与审计查询。**为空时相关接口返回 503**（未启用）。 |

### 就绪探针

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `READY_CHECK_MINIO` | `true` | `GET /ready` 是否检查 MinIO。 |
| `READY_CHECK_MODEL_GATEWAY` | `false` | `GET /ready` 是否探测模型网关健康 URL。 |

详见 [09-tool-gateway.md](09-tool-gateway.md)、[49-mcp-integration-assessment.md](49-mcp-integration-assessment.md)。

---

## 数据库配置表

### system_config（通用 KV）

```yaml
key: runspec_schema_version_current
value: "1"
说明: 当前支持的 RunSpec schema 版本

key: degradation.default_level
value: "0"
说明: 默认降级级别（0=无降级）

key: audit.default_level
value: "minimal"
说明: 默认审计档位

key: audit.default_retain_days
value: "90"
说明: 默认审计保留天数

key: session.default_timeout_minutes
value: "30"
说明: 会话默认超时（分钟）

key: mau.threshold.default
value: "5"
说明: 默认 MAU 体检阈值

key: agent.max_versions_keep
value: "10"
说明: Agent 保留最大历史版本数

key: skill.max_versions_keep
value: "50"
说明: Skill 保留最大历史版本数
```

---

## 模型配置文件

### `src/config/models.yaml`

```yaml
models:
  qwen3-32b:
    provider: local              # local / openai_compatible
    endpoint: http://.../v1      # 模型服务地址
    max_tokens: 32768            # 最大上下文长度
    rpm: 100                     # 每分钟请求数上限
    tpm: 100000                  # 每分钟 token 数上限
    health_endpoint: http://...  # 健康检查地址

  bge-m3:
    provider: local
    endpoint: http://.../v1
    type: embedding              # 特殊标记：embedding 模型
    batch_size: 32               # 批处理大小
```

**加载时机**：服务启动时一次性加载，存入内存。修改后需重启服务生效。

---

## Platform Policy 配置

存储于数据库 `platform_policies` 表，通过管理后台维护。

```yaml
id: default
version: 1
prompt: |
  你是央企内部智能助手。你的回答必须：
  1. 不涉及国家秘密、商业秘密
  2. 不给出法律意见替代专业律师
  3. 不泄露其他用户信息
  4. 不确定时明确标注"需人工复核"
  5. 引用公司制度时必须标注文号和生效日期
enabled: true
```

---

## Org Policy 配置

存储于数据库 `org_policies` 表，各部门管理员维护。

```yaml
id: legal_policy_v2
department: legal
version: 2
prompt: |
  你是法务部智能助手。引用制度时必须标注文号和生效日期。
enabled: true
```

---

## Agent App 配置

主存储：数据库 `agent_apps` 表 + `agent_versions` 表。
备份：对象存储 `agents/{agent_id}/{version}/agent.yaml`。

完整字段见 [03-agent-app-spec.md](03-agent-app-spec.md)。

---

## 配置加载优先级汇总

```
环境变量（如 DATABASE_URL）
  ↓ 覆盖
.env 文件（开发环境）
  ↓ 覆盖
K8s ConfigMap / Secret（生产环境）
  ↓ 覆盖
代码默认值（Pydantic Settings default）
```

**Pydantic Settings 行为**：
- 先读 `.env` 文件
- 再读环境变量（环境变量优先级高于 `.env`）
- 最后用代码默认值填充缺失项

---

## 生产环境配置管理规范

1. **敏感信息**（密钥、密码）必须走 K8s Secret 或外部 Vault，禁止写入 ConfigMap
2. **非敏感配置**走 K8s ConfigMap，修改后滚动重启 Pod 生效
3. **数据库配置**（如 `system_config`）修改后最长 5 分钟生效（受缓存 TTL 限制）
4. **模型配置**修改需重启服务，建议在维护窗口执行
5. **配置变更审计**：所有 `system_config`、`platform_policies`、`org_policies` 的修改记录写入审计日志
