# 36. 故障排查手册

> 版本：v0.6 · 2026-05-06

---

## 排查原则

1. **先看 trace_id**：所有请求入口注入 `X-Trace-Id`，按 trace_id 在 Grafana/Jaeger 中检索全链路
2. **再看日志级别**：ERROR 级日志带 `error_code`，按错误码速查本节
3. **最后看指标**：Prometheus `af_*` 指标判断是单点问题还是全局问题

---

## 按错误码速查

| 错误码 | 常见原因 | 排查步骤 |
|--------|---------|---------|
| `SESSION_EXPIRED` | session cookie 超过 30 分钟无活动 | 检查 `POST /auth/heartbeat` 是否正常触发；检查 Redis session key TTL |
| `TOKEN_REUSED` | short-lived JWT 被重复使用 | 检查 portal 是否重复用同一 token 开多个 tab；检查后端 jti 黑名单 |
| `COMPILE_ERROR` | Skill Compiler 失败 | 检查 `agent.yaml` 语法；检查 Skill 包完整性；查看 Compiler 日志中的具体错误文件 |
| `SCHEMA_VALIDATION_FAILED` | 模型输出不符合 JSON Schema | 检查 Agent/Skill 的 schema 定义；检查模型 temperature 是否过高；最多重试 2 次仍失败则记录 |
| `TOOL_NOT_ALLOWED` | 模型尝试调用白名单外工具 | 检查 `RunSpec.allowed_tools`；检查模型是否 hallucinate 工具名； Skill 的 `tools.require` 是否越界 |
| `TOOL_TIMEOUT` | 工具调用超时 | 检查 Tool 的 `timeout_seconds` 配置；检查下游服务（doc-worker / kb）健康状态 |
| `MODEL_UNAVAILABLE` | 全部模型不可用或队列满 | 检查模型集群健康端点；检查 `af_model_queue_length` 指标；检查降级级别是否手动设高 |
| `TOKEN_QUOTA_EXCEEDED` | token 预算耗尽 | 检查 `token_quotas` 表该 scope 的 used/budget；检查是否为月初重置异常 |
| `UPSTREAM_ERROR` | 下游服务返回 5xx | 检查 doc-worker / kb / 模型服务的独立健康状态 |
| `DEGRADATION_ACTIVE` | 当前处于降级状态 | 检查 `degradation_events` 表最近事件；检查 Grafana L0 仪表盘 |

---

## 按场景排查

### 用户无法打开 Widget（白屏 / 403 / 无 Agent 列表）

```
1. 浏览器 DevTools Network → 检查 /auth/exchange 是否 200
   └─ 401 → portal-JWT 过期或 portal 公钥配置错误
   └─ 403 → 用户无该 Agent 权限（检查 RBAC）
2. 检查 /auth/session 是否 Set-Cookie 成功
   └─ 无 cookie → SameSite=Strict 跨域问题（确认 portal 和 widget 域名在 ALLOWED_ORIGINS）
3. 检查 GET /agents 返回是否为空
   └─ 空 → 用户确实无权限，或 agent_apps 表中 lifecycle_state 非 active
```

### SSE 流式输出中断（消息到一半停了）

```
1. 检查浏览器 Network → EventSource / fetch stream 状态
   └─ 连接断开 → 检查 Nginx/网关超时配置（proxy_read_timeout 需 > 90s）
2. 后端检查 Runner 日志
   └─ session lock 等待 → 同一 session 并发请求（检查 widget 是否意外重连）
   └─ 模型调用 timeout → 检查模型集群负载
3. 检查 af_agent_request_duration_seconds 的 P99
   └─ P99 > 30s → 可能触发网关超时
```

### Chat SSE 报 `HTTP 502` 且 body 为空（`MODEL_UNAVAILABLE`）

```
1. 看 RunSpec 里 runtime.model（init 返回的 run_id 对应 run_specs 或日志）
   └─ 若为 qwen3-32b 且 models.yaml 中其 endpoint 为 http://localhost:8000/v1
      → 请求会打到本 API 自身，常见 502/空包；应改为 MiniMax 或真实 vLLM 地址
2. 核对 MiniMax：密钥站点与 Base URL 一致（国内 api.minimaxi.com/v1，国际 api.minimax.io/v1）
3. 自检：cd backend && uv run python scripts/test_minimax_openai_chat.py
4. 仍 502：检查公司 HTTP 代理 / MITM；客户端已关闭 HTTP/2 流式（http2=False）以降低中间件异常
```

### 文件上传失败

```
1. 前端预检：确认 ui_config.attachments.accept 和 max_size_mb 包含该文件类型
2. 后端二次校验：检查 /upload 返回的错误码
   └─ FILE_TOO_LARGE → 检查 limits.max_file_size（字节）与前端 max_size_mb 是否一致
   └─ INVALID_FILE_TYPE → MIME type 识别错误（某些 Windows 环境 mime 为 application/octet-stream）
3. Doc Worker 检查
   └─ 大文件（>10MB）需异步解析，检查 Redis Streams 队列堆积
```

### 审计日志未写入

```
1. 检查 audit.level 是否为 minimal（标准配置）
2. 检查 Redis Streams 消费者组是否正常运行
   └─ redis-cli XINFO GROUPS audit_log_stream
3. 检查 PostgreSQL 分区是否已创建（按月分区）
   └─ 缺失分区会导致写入报错
4. 检查磁盘空间（audit_logs 表膨胀）
```

### 模型降级不恢复

```
1. 检查 degradation_events 表
   └─ manual 触发 → 需手动调 POST /admin/degradation/recover
   └─ auto 触发 → 检查触发指标是否已连续 5 分钟低于阈值
2. 检查 Grafana L0 仪表盘
   └─ af_degradation_level gauge 当前值
   └─ LLM 队列 P99 是否仍高于阈值
3. 检查模型集群健康
   └─ 全部模型 down → 降级不会自动恢复（无可用模型）
```

---

## 常用诊断命令

```bash
# Redis 检查 session
redis-cli GET session:sess_abc123

# Redis 检查 checkpoint
redis-cli HGETALL checkpoint:sess_abc123:cp_001

# Redis 检查队列长度
redis-cli XLEN audit_log_stream
redis-cli LLEN doc_worker_queue

# PostgreSQL 检查慢查询
SELECT * FROM pg_stat_activity WHERE state = 'active' ORDER BY query_start;

# MinIO 检查对象存储
mc ls local/agent-factory/skills/

# 查看最近降级事件
psql -c "SELECT * FROM degradation_events ORDER BY started_at DESC LIMIT 5;"

# 查看某 Agent 预算
psql -c "SELECT * FROM token_quotas WHERE scope_id = 'legal' AND period_start = '2026-05-01';"
```

---

## 联系运维升级

以下情况需立即升级至平台运维团队：

- 全部模型集群不可用时长大于 5 分钟
- PostgreSQL 主从延迟超过 10 秒
- Redis 主从切换或内存使用率超过 90%
- 任意归档文件 MD5 校验失败
- `degradation_exempt=true` 的关键 Agent 也出现异常
