# 32. 可观测性设计

> 版本：v0.6 · 2026-05-06

---

## 设计目标

为 Agent App Factory 建立**生产级可观测性体系**，满足：

1. **故障快速定位**：从用户报障到锁定根因 < 5 分钟
2. **容量提前感知**：资源瓶颈在影响用户前被预警
3. **业务健康洞察**：Agent 效果、用户满意度可量化
4. **合规安全边界**：观测数据与审计数据物理隔离，观测系统不触碰用户对话内容

**与审计的边界**（详见 [12-security-audit.md](12-security-audit.md)）：

| 维度 | 观测性（Observability） | 审计（Audit） |
|------|------------------------|--------------|
| 目的 | 系统健康、性能、故障排查 | 合规留档、事后追查 |
| 数据粒度 | 聚合指标、采样 trace | 每次执行的完整细节 |
| 保留期 | 15~90 天 | 90 天 ~ 5 年 |
| 包含用户内容 | **绝不包含** prompt / 输出 / 附件 | 按档位存储 |
| 查询模式 | 实时监控、聚合报表 | 单条明细追溯 |

---

## 三支柱架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Metrics      │     │     Logs        │     │    Traces       │
│  (Prometheus)   │     │  (Loki / 文件)  │     │ (OpenTelemetry) │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │      Grafana            │
                    │  (Dashboard + Alerting) │
                    └─────────────────────────┘
```

---

## Metrics 指标规范（Prometheus）

### 暴露方式

- **后端**：`prometheus-fastapi-instrumentator` 自动暴露 `/metrics`
- **Worker**：Doc Worker / Script Worker 内置 `prometheus_client` push 或 HTTP server
- **前端**：通过 `navigator.sendBeacon` 上报至专用 `/metrics/frontend` 接收端
- **仓库运维样例**（与 [plan.md](../plan.md) §12 对账）：[`deploy/prometheus/rules/agent_factory.rules.yml`](../deploy/prometheus/rules/agent_factory.rules.yml)（`promtool check rules`）、[`deploy/grafana/dashboards/agent-factory-overview.json`](../deploy/grafana/dashboards/agent-factory-overview.json)（导入 Grafana 后绑定 Prometheus；阈值按环境调优）

### 核心指标命名规范

所有指标前缀为 `af_`（agent_factory），标签使用 snake_case。

#### 系统层

```
af_http_requests_total{method, route, status_code}
af_http_request_duration_seconds{method, route, status_code}  # histogram
af_http_request_duration_seconds_bucket
af_http_request_duration_seconds_sum
af_http_request_duration_seconds_count

af_model_requests_total{model_id, status}
af_model_request_duration_seconds{model_id, status}
af_model_tokens_total{model_id, direction}  # direction=in/out
af_model_queue_length{concurrency_class}  # privileged / interactive / document / batch
af_model_fallback_total{from_model, to_model, reason}

af_tool_calls_total{tool_id, status}
af_tool_call_duration_seconds{tool_id, status}
af_tool_gateway_rejections_total{tool_id, reason}  # permission / rate_limit / circuit_breaker

af_active_sessions{agent_id}
af_session_lock_wait_seconds{agent_id}

af_degradation_level  # gauge: 当前全局降级级别 0~5（与 DegradationService 一致）
```

#### Agent 层

```
af_agent_requests_total{agent_id, status}
af_agent_request_duration_seconds{agent_id, status}
af_agent_errors_total{agent_id, error_code}
af_agent_token_usage_total{agent_id, user_type}  # user_type=internal/external
af_agent_turns_total{agent_id}  # 每轮对话计数
af_agent_schema_validation_total{agent_id, result}  # result=pass/fail/retry
af_agent_tool_call_pattern_total{agent_id, tool_sequence}  # 例如 "kb.search→doc.extract"
```

#### 业务层

```
af_dau_total{date, department}      # 日活（去重 user_id_hash）
af_mau_total{agent_id, month}       # 月活
af_feedback_total{agent_id, sentiment}  # sentiment=up/down
af_feedback_rate{agent_id}          # 反馈率 = 有反馈的消息数 / 总消息数
af_new_conversations_total{agent_id, date}
af_uploads_total{mime_type, status}
```

#### 前端层

```
af_widget_page_load_seconds{agent_id}
af_widget_ttfb_seconds{agent_id}    # Time To First Byte（SSE 首包）
af_widget_sse_reconnect_total{agent_id, reason}
af_widget_error_total{error_type, agent_id}  # error_type=js/network/timeout
af_widget_lcp_seconds               # Largest Contentful Paint
```

---

## Logs 规范（Loki）

### 日志级别与场景

| 级别 | 场景 | 是否告警 |
|------|------|---------|
| DEBUG | 开发调试，生产关闭 | 否 |
| INFO | 关键业务流程节点（RunSpec 编译完成、会话创建、Agent 切换） | 否 |
| WARNING | 非致命异常（模型降级、工具 fallback、限流触发） | 否（ Grafana 面板展示） |
| ERROR | 业务失败（Skill 编译失败、Tool 调用异常、Schema 校验连续失败） | 是（钉钉 warning） |
| CRITICAL | 系统级故障（数据库连不上、Redis 宕机、全部模型不可用） | 是（钉钉 + 短信 + 电话） |

### 结构化日志字段（JSON 格式）

```json
{
  "timestamp": "2026-05-07T14:30:00.123Z",
  "level": "ERROR",
  "logger": "agent_factory.services.compiler_service",
  "message": "RunSpec compilation failed",
  "trace_id": "req_abc123",
  "span_id": "span_def456",
  "agent_id": "contract-review-agent",
  "user_id_hash": "a1b2c3...",
  "error_code": "COMPILE_ERROR",
  "error_message": "SKILL.md references missing file: checklist.md",
  "context": {
    "skill_id": "clause-review",
    "skill_version": "0.1.0"
  }
}
```

**敏感信息过滤**：日志中**绝不出现**以下内容：
- 用户原始 prompt / 模型输出
- 文件内容摘要（file_id 可以出现）
- portal-JWT 或 short-lived JWT（出现即 mask）
- 真实 user_id（使用 user_id_hash）

---

## Traces 规范（OpenTelemetry）

### 后端可选接入（本仓库）

- **开关**：`OTEL_ENABLED=true`，并设置 **`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`**（OTLP/HTTP，例如 `http://otel-collector:4318/v1/traces`）。
- **依赖**：`uv sync --extra observability`（安装 `opentelemetry-*` 与 FastAPI 插桩）；未安装包时开启开关仅打日志告警，不中断服务。
- **实现**：`infra/otel.py` 在 `create_app` 末尾注册 `TracerProvider` + `BatchSpanProcessor` + `FastAPIInstrumentor`；采样率为 **`OTEL_TRACES_SAMPLER_RATIO`**（`TraceIdRatioBased`）。
- 变量说明见 [31-configuration-reference.md](31-configuration-reference.md)。

### 传播方式

- 入口（API Gateway）生成 `trace_id`，注入 HTTP response header `X-Trace-Id`
- 内部服务间调用通过 **W3C Trace Context** 传递 traceparent header
- Redis / PostgreSQL 操作作为子 span，标注执行语句类型（不记录参数值）

### 关键 Trace 场景

```
POST /agents/{agent_id}/chat
├── span: auth_middleware (验证 session)
├── span: compile_runspec
│   ├── span: db.query_agent_config
│   ├── span: skill_registry.load_skill
│   └── span: permission_intersection
├── span: runner.execute
│   ├── span: model.call (turn 1)
│   │   ├── span: model_gateway.route
│   │   └── span: model_client.chat_completion
│   ├── span: tool.call (doc.extract)
│   │   ├── span: tool_gateway.validate
│   │   └── span: doc_worker.extract
│   └── span: model.call (turn 2)
└── span: emit_audit_log (异步)
```

### 采样策略

| 环境 | 采样率 | 说明 |
|------|--------|------|
| development | 100% | 全量采集 |
| staging | 100% | 全量采集 |
| production | 1%（头部采样）+ 错误全采 | 正常请求 1%，错误/trace_id 指定请求 100% |

**尾部采样**：生产环境如需详细分析某次用户报障，通过 `X-Trace-Id` 在 Jaeger / Grafana Tempo 中检索，无需全局高采样。

---

## Grafana 仪表盘分层

### L0 · 全局健康（值班大屏）

- 全局 QPS、P99 延迟、错误率
- 降级级别指示灯
- 模型集群健康状态（qwen3-32b / 14b / 8b）
- 未处理 critical 告警数

### L1 · Agent 运营（业务部门视角）

- 本部门 Agent 列表：请求量、错误率、平均延迟
- Token 消耗趋势（按天 / 按 Agent）
- 用户反馈分布（👍 / 👎 / 反馈率）
- MAU 趋势与 retention gate 预警

### L2 · 技术排查（开发/运维视角）

- 按 trace_id 检索全链路
- 模型调用瀑布图（每轮耗时、token 数）
- Tool Gateway 拒绝原因分布
- Session Lock 等待队列
- Redis / PostgreSQL / MinIO 资源使用

### L3 · 前端体验（产品视角）

- 页面加载性能分布（LCP / FCP / TTFB）
- SSE 连接成功率、重连频率
- JS 错误率（按错误类型聚合）
- 浏览器兼容性分布

---

## 告警路由规则

| 级别 | 通知渠道 | 升级策略 | 静默窗口 |
|------|---------|---------|---------|
| warning | 钉钉群 | 无 | 同类型 30 分钟内只发 1 条 |
| critical | 钉钉群 + 短信 | 15 分钟内未恢复 → 电话通知值班经理 | 同类型 10 分钟内只发 1 条 |

**告警抑制**：
- 降级状态（level > 0）期间，因降级触发的 P99 延迟告警自动抑制
- 模型集群维护窗口（通过 API `/admin/degradation/level` 标记）期间，对应模型的 health 告警抑制

---

## 前端可观测性实现

```typescript
// src/utils/telemetry.ts
export function reportMetric(name: string, value: number, labels: Record<string, string>) {
  navigator.sendBeacon('/api/v1/metrics/frontend', JSON.stringify({
    name: `af_widget_${name}`,
    value,
    labels,
    timestamp: Date.now(),
  }));
}

// 性能指标采集
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    if (entry.entryType === 'largest-contentful-paint') {
      reportMetric('lcp_seconds', entry.startTime / 1000, { agent_id: currentAgentId });
    }
  }
}).observe({ entryTypes: ['largest-contentful-paint'] });

// JS 错误采集
window.addEventListener('error', (e) => {
  reportMetric('error_total', 1, {
    error_type: 'js',
    agent_id: currentAgentId,
    message: e.message.substring(0, 100),
  });
});
```

---

## SLA 目标与性能基准

### P0 阶段 SLA 承诺

| 指标 | 目标值 | 测量方式 | 违约后果 |
|------|--------|---------|---------|
| 可用性 | ≥ 99.5%（月度） | 所有 API 200/204 响应占比 | 低于 99% 触发 critical 告警 |
| 端到端延迟（P50） | ≤ 3s（首 token） | `/agents/{id}/chat` 从请求到首 SSE 事件 | P50 持续 > 5s 触发自动降级 |
| 端到端延迟（P99） | ≤ 15s（首 token） | 同上 | P99 持续 > 30s 触发模型 fallback |
| 模型调用延迟（P50） | ≤ 2s（首 token） | 模型网关内部队列出队到首 token | P50 持续 > 5s 标记模型 degraded |
| 模型调用延迟（P99） | ≤ 10s（首 token） | 同上 | P99 持续 > 15s 自动 fallback |
| 工具调用延迟（P99） | ≤ 5s | Tool Gateway 收到请求到返回结果 | P99 持续 > 5s 触发熔断 |
| SSE 流式完整性 | ≥ 99.9% | `done` 事件正常到达 / 总请求数 | 异常中断率 > 0.5% 触发排查 |
| 页面加载（LCP） | ≤ 2.5s | widget 首屏 Largest Contentful Paint | 持续 > 4s 触发前端优化工单 |
| 会话恢复成功率 | ≥ 99% | `resume` API 成功 / 总刷新次数 | 低于 95% 触发排查 |

### 容量基准（单实例）

基于 [18-deployment-ops.md](18-deployment-ops.md) 的容量规划，单 Core 实例（4C8G）的性能基准：

| 场景 | 并发请求 | QPS | 说明 |
|------|---------|-----|------|
| 纯对话（无工具） | 50 | 10 | 轻量，主要瓶颈在模型网关队列 |
| 含 1 次 kb.search | 30 | 5 | 工具调用增加一次网络往返 |
| 含 1 次 doc.extract | 20 | 3 | 文档解析 Worker 成为瓶颈 |
| 混合场景（平均 2 次工具调用） | 25 | 4 | 综合基准 |

**扩容触发条件**：
- CPU 持续 5 分钟 > 70% → 增加 Core 实例
- Redis 连接数 > 80% 最大连接 → 增加连接池或扩容 Redis
- 模型队列长度持续 > 500 → 增加模型后端实例或触发降级

---

## 与现有文档的衔接

- **告警阈值配置** → [18-deployment-ops.md](18-deployment-ops.md) §监控告警
- **统计汇总定时任务** → [21-cron-jobs.md](21-cron-jobs.md) §Agent 使用统计汇总、反馈数据汇总
- **审计日志（与观测性隔离）** → [12-security-audit.md](12-security-audit.md)
- **降级状态指示灯** → [13-concurrency.md](13-concurrency.md) §降级策略
- **模型健康探测** → [21-cron-jobs.md](21-cron-jobs.md) §模型健康探测
