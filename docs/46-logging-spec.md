# 46. 日志规范

> 版本：v0.6 · 2026-05-06

---

## 目标

统一全系统（后端、前端、Nginx、Worker）的日志格式、级别、字段和传播规则，确保：

1. **运维可排查**——通过 trace_id 串联全链路
2. **合规不泄露**——敏感信息自动脱敏
3. **成本可控**——采样策略避免日志洪水

---

## 日志分层

| 层级 | 来源 | 收集方式 | 保留期 | 说明 |
|------|------|---------|--------|------|
| 访问日志 | Nginx | 文件 + Loki | 30 天 | HTTP 请求记录（URL 中 token 已 mask） |
| 应用日志 | Python / Node.js | stdout + Loki | 30 天 | 业务逻辑、异常堆栈 |
| 审计日志 | 核心业务表 | PostgreSQL | 90 天 | 合规审计（与观测性隔离） |
| 错误日志 | 所有服务 | Loki + 告警 | 90 天 | ERROR / CRITICAL 级别 |
| 前端日志 | Chat Widget | 不上报（本地） | — | 仅本地 console，不上传服务器 |

---

## 结构化日志格式（JSON）

所有应用日志必须输出为单行 JSON：

```json
{
  "timestamp": "2026-05-07T14:30:00.123+08:00",
  "level": "ERROR",
  "logger": "agent_factory.services.compiler_service",
  "message": "RunSpec compilation failed",
  "trace_id": "req_abc123",
  "span_id": "span_def456",
  "agent_id": "contract-review-agent",
  "user_id_hash": "a1b2c3...",
  "run_id": "run_20260507_001",
  "session_id": "sess_xyz789",
  "duration_ms": 150,
  "error_code": "SKILL_NOT_FOUND",
  "error_message": "Skill clause-review v0.2.0 not found in registry",
  "stack_trace": "...",
  "env": "production",
  "version": "0.1.0"
}
```

### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | ISO 8601 | 带时区（+08:00） |
| `level` | string | DEBUG / INFO / WARNING / ERROR / CRITICAL |
| `logger` | string | 模块路径，如 `agent_factory.services.compiler_service` |
| `message` | string | 简短描述，不含敏感信息 |
| `trace_id` | string | 全链路唯一标识，由 API Gateway 生成 |
| `env` | string | `development` / `staging` / `production` |
| `version` | string | 服务版本号 |

### 可选字段（按场景填充）

| 字段 | 场景 | 说明 |
|------|------|------|
| `span_id` | 分布式追踪 | 当前 span 标识 |
| `agent_id` | Agent 相关操作 | 不涉及则省略 |
| `user_id_hash` | 用户相关操作 | SHA-256 哈希，不存明文 |
| `run_id` | 单次运行 | RunSpec 编译后生成 |
| `session_id` | 会话级 | 长会话标识 |
| `duration_ms` | 耗时操作 | 数据库查询、模型调用、工具执行 |
| `error_code` | 错误场景 | 业务错误码，如 `SKILL_NOT_FOUND` |
| `error_message` | 错误场景 | 脱敏后的错误描述 |
| `stack_trace` | ERROR+ | 异常堆栈，生产环境截断前 50 行 |

---

## 日志级别定义

| 级别 | 使用场景 | 是否告警 | 采样策略 |
|------|---------|---------|---------|
| **DEBUG** | 开发调试、详细变量值 | 否 | dev 100%，staging 100%，prod 1% |
| **INFO** | 关键路径节点（请求开始/结束、编译完成、工具调用成功） | 否 | dev/staging 100%，prod 10% |
| **WARNING** | 可恢复异常（模型 fallback、限流触发、缓存失效重查） | 否（企微通知） | 100% |
| **ERROR** | 业务错误（Skill 未找到、参数校验失败、模型超时） | 是（企微） | 100% |
| **CRITICAL** | 系统级故障（数据库连不上、Redis 宕机、全部模型不可用） | 是（企微 + 短信 + 电话） | 100% |

**关键约束**：
- 生产环境 **绝不输出 DEBUG 级别的模型 prompt / 输出内容**
- 即使开 full 审计，观测性日志与审计数据**物理隔离**

---

## 敏感信息脱敏规则

日志中**绝不出现**以下内容：

| 数据类型 | 脱敏方式 | 示例 |
|---------|---------|------|
| 用户原始 prompt | 完全禁止 | — |
| 模型输出内容 | 完全禁止 | — |
| 文件内容摘要 | 完全禁止 | 只允许出现 `file_id` |
| JWT / Session Token | mask 中间段 | `eyJhbG...ciOiJ` |
| 模型 API Key | mask 前 4 后 4 | `sk-ab****xyz` |
| 数据库密码 | 完全禁止 | 只显示连接是否成功 |
| user_id 明文 | 使用哈希 | `user_id_hash: a1b2...` |
| 合同/公文正文 | 完全禁止 | 只允许出现 `doc.extract 成功` |

**Nginx 层特殊处理**：

```nginx
# /etc/nginx/conf.d/agent-factory.conf
# access_log 使用 masked 格式，自动将 URL 中的 token 参数替换为 [MASKED]
access_log /var/log/nginx/agent-factory.access.log masked;
```

---

## trace_id 传播规范

### 生成

- 入口（API Gateway）生成 `trace_id`，格式：`req_{uuid32}`
- 注入 HTTP Response Header：`X-Trace-Id`

### 传递

```
API Gateway
  ↓ trace_id in request context
Core Service
  ↓ trace_id in HTTP header / RPC metadata
Skill Compiler / Agent Runner / Tool Gateway / Model Gateway
  ↓ trace_id in DB connection options / Redis command kwargs
PostgreSQL / Redis / MinIO
```

### 前端消费

- widget 在收到首个 SSE 事件时读取 `X-Trace-Id`
- 用户点"反馈"时，前端将 `trace_id` 随反馈数据上报
- 运维收到用户报障时，直接用 `trace_id` 在 Grafana 中检索全链路

---

## 日志采样策略

| 环境 | INFO 采样率 | DEBUG 采样率 | 错误全采 | 指定 trace 全采 |
|------|------------|-------------|---------|---------------|
| development | 100% | 100% | 是 | 是 |
| staging | 100% | 100% | 是 | 是 |
| production | 10% | 1% | 是 | 是 |

**指定 trace 全采**：通过 HTTP Header `X-Force-Trace: true` 触发（仅内部调试接口可用）。

---

## 前端日志策略

**原则**：Chat Widget 的日志**不上报服务器**，仅输出到浏览器 console。

```typescript
// widget/src/utils/logger.ts
const logger = {
  debug: (...args: any[]) => {
    if (import.meta.env.DEV) console.debug('[Widget]', ...args);
  },
  info: (...args: any[]) => {
    if (import.meta.env.DEV) console.info('[Widget]', ...args);
  },
  warn: (...args: any[]) => console.warn('[Widget]', ...args),
  error: (...args: any[]) => console.error('[Widget]', ...args),
};
```

**禁止**：
- 禁止将用户消息、模型输出、文件内容发送到任何日志收集服务
- 禁止引入前端 APM（Sentry、GA 等），数据外泄风险不可控

**例外——前端可上报的聚合指标白名单**

以下数据允许前端以**聚合/脱敏**方式上报，用于运营仪表盘，但严禁包含任何用户具体内容：

| 指标 | 类型 | 说明 |
|------|------|------|
| `ui_config.render_success` | boolean | 仅标记渲染是否成功（不含界面截图或 DOM 内容） |
| `widget.performance.lcp` / `fid` / `cls` | number | Web Vitals 性能数值 |
| `widget.error_count` | counter | 错误计数（不含错误详情或堆栈） |
| `widget.feedback_rate` | float | 反馈率聚合百分比 |

**上报原则**：仅上报聚合统计值和纯数值指标，禁止上报任何包含用户消息、模型输出、文件内容、会话文本的字段。

---

## 与现有文档的衔接

- **可观测性三支柱** → [32-observability-design.md](32-observability-design.md)
- **部署与运维日志管理** → [18-deployment-ops.md](18-deployment-ops.md) §日志管理
- **Nginx 日志 mask 配置** → [41-nginx-config.md](41-nginx-config.md)
- **审计日志（与观测性隔离）** → [12-security-audit.md](12-security-audit.md)
- **安全架构敏感数据分级** → [45-security-architecture.md](45-security-architecture.md)
