# 19. API 接口参考

> 版本：v0.6 · 2026-05-06

---

本文档汇总 **HTTP API** 的对外契约，与 [prd.md](../prd.md) 中 portal 集成（§4.5、§10.4）、Skill/Tool Registry（§8.5~8.6）、审计与观测（§10.2、§10.5、§10.6）、降级运维（§9）及路线图（§11）对齐。实现细节见各专题文档。

### 专题文档索引

- 认证 / SSO / widget → [06-api-gateway.md](06-api-gateway.md)、[11-chat-widget.md](11-chat-widget.md)
- Skill Registry → [04-skill-package-spec.md](04-skill-package-spec.md)
- Tool Registry → [09-tool-gateway.md](09-tool-gateway.md)
- Agent Runner / SSE 语义 → [08-agent-runner.md](08-agent-runner.md)
- P0 裁剪 → [34-p0-delivery-spec.md](34-p0-delivery-spec.md)、[47-prd-alignment.md](47-prd-alignment.md)

### PRD 需求 → API 覆盖矩阵（摘要）

| PRD 内容 | API / 行为 |
|----------|------------|
| §4.5 独立子站 + JWT URL | 浏览器加载 widget；**不落单独 REST**，后续走 `/auth/session` |
| §10.4 短 JWT + jti 一次性 | `POST /auth/exchange`、`POST /auth/session`、`POST /auth/heartbeat` |
| §10.5 MAU 最小元数据 | **`POST .../init` 成功时服务端写 `agent_usage_log`**（无单独 MAU 上报接口） |
| §8.5 Skill Registry | `/skills*` |
| §8.6 Tool Registry | `/tools*` |
| §7 RunSpec 编译入口 | `POST .../init`（内部 Compiler） |
| §9 降级 | `POST /admin/degradation/*` + Runner 返回码 `DEGRADATION_ACTIVE` |
| §10.6 观测 | `GET /metrics`、`POST /metrics/frontend`；管理端 **`GET /admin/product-metrics/summary`**（DAU/MAU 代理、新会话、新 Agent、反馈聚合） |
| §11.5 灰度发布 | `POST .../releases`、`GET .../versions` |

### 交付阶段与接口可用性

| 阶段 | 说明 |
|------|------|
| **P0** | 用户侧 `/auth/*`、`/agents/*`（含 chat/upload/resume/feedback）、minimal **审计写入**（异步，无查询 UI）、模型与 Tool MVP、`POST /metrics/frontend` |
| **P0.5** | **审计查询** `/audit/*` 管理台消费端、报表导出增强（写入已在 P0） |
| **P1+** | Tool 扩展、schema/评测闭环、内部 API 类 Tool 逐个接入 |
| **P2+** | 受控脚本 Worker；RunSpec `script_hooks` 非空时的执行链路 |

---

## 统一约定

### 基地址

```
https://agent.company.com/api/v1
```

下文所列路径（如 `/auth/exchange`、`/agents`）均 **相对于上述前缀**。运维探针 `GET /health`、`GET /ready`、`GET /metrics` 常挂载在 **网关根路径**（无前缀），与 Ingress 配置一致（见 [40-k8s-manifests.md](40-k8s-manifests.md)）。

### 认证方式

| 阶段 | 方式 | 说明 |
|------|------|------|
| portal → widget | short-lived JWT（URL query param） | 5 分钟有效，一次性 |
| widget → API | session cookie | 30 分钟有效，心跳延长 |
| 管理员接口 | admin JWT（Authorization header） | 长期有效，独立签发 |

### 统一错误响应

```json
{
  "error": {
    "code": "INVALID_PARAMS",
    "message": "agent_id is required",
    "request_id": "req_abc123"
  }
}
```

### HTTP 状态码

| 码 | 场景 |
|----|------|
| 200 | 成功 |
| 202 | 已接受（如 beacon 类上报） |
| 400 | 参数错误 / 业务校验失败 |
| 401 | 未认证 / session 过期 |
| 403 | 无权访问 / Agent 未激活 |
| 404 | 资源不存在 |
| 409 | 状态冲突（如重复发布、并发修改） |
| 429 | 限流 |
| 500 | 内部错误 |
| 502 | 上游错误 |
| 503 | 服务不可用（模型全员故障、强制降级等） |

### 通用请求约定

- **`request_id`**：服务端生成的追踪 ID，响应体 `error.request_id` 与日志对齐；可选请求头 `X-Request-ID` 由网关透传。
- **时间**：请求/响应体时间字段均为 **ISO 8601 UTC**，除非文档另有说明。
- **分页**：列表接口默认 `page=1`、`page_size=20`，`page_size` 上限见各接口。
- **Cookie**：用户侧接口使用 **`session_id`** HttpOnly Cookie（名依部署配置，默认见 [31-configuration-reference.md](31-configuration-reference.md)）。

### 全局错误码表

| 错误码 | HTTP 状态 | 场景 | 用户提示建议 |
|--------|-----------|------|-------------|
| `INVALID_PARAMS` | 400 | 请求参数缺失或格式错误 | 检查必填字段 |
| `AGENT_NOT_FOUND` | 404 | Agent ID 不存在 | 确认 Agent 是否已下架 |
| `AGENT_INACTIVE` | 403 | Agent 处于 cold / archived 状态 | 联系管理员激活 |
| `SKILL_NOT_FOUND` | 404 | Skill ID 或版本不存在 | 确认 Skill 是否已注册 |
| `SESSION_EXPIRED` | 401 | session cookie 过期 | 重新从 portal 进入 |
| `SESSION_REQUIRED` | 401 | 请求未携带 session | 重新从 portal 进入 |
| `TOKEN_EXPIRED` | 401 | short-lived JWT 已过期 | 关闭 tab，从 portal 重新打开应用 |
| `TOKEN_REUSED` | 401 | jti 已消费过（重放） | 同上 |
| `FORBIDDEN` | 403 | 用户无该操作权限 | 联系管理员申请权限 |
| `RATE_LIMITED` | 429 | 触发 IP / 用户 / 全局限流 | 稍后重试 |
| `TOKEN_QUOTA_EXCEEDED` | 429 | 当月 token 预算耗尽 | 联系部门管理员 |
| `COMPILE_ERROR` | 400 | Skill Compiler 编译 RunSpec 失败 | 检查 agent.yaml / Skill 配置 |
| `SCHEMA_VALIDATION_FAILED` | 400 | 模型输出不符合 JSON Schema | 重试或联系 Skill 开发者 |
| `TOOL_NOT_ALLOWED` | 403 | 模型尝试调用不在 RunSpec.allowed_tools 中的工具 | 系统内部错误，需排查 |
| `TOOL_TIMEOUT` | 500 | 工具调用超时（如 doc.extract 大文件） | 检查文件是否过大或损坏 |
| `MODEL_UNAVAILABLE` | 503 | 模型网关无可用模型（全部降级/故障） | 等待模型恢复或联系运维 |
| `DEGRADATION_ACTIVE` | 503 | 当前处于降级状态，部分功能受限 | 等待恢复或联系运维 |
| `INTERNAL_ERROR` | 500 | 未预期的内部错误 | 联系运维并提供 request_id |
| `FILE_TOO_LARGE` | 400 | 上传文件超过限制 | 拆分文件或压缩后上传 |
| `INVALID_FILE_TYPE` | 400 | 文件格式不在白名单 | 转换为支持的格式 |
| `UPSTREAM_ERROR` | 502 | 下游服务（模型 / 知识库 / 文档解析）返回错误 | 稍后重试 |

---

## 运维与健康检查（无鉴权或内网 ACL）

以下为 **基础设施** 契约，与 PRD §10.6（观测性）及 K8s 部署一致；**勿**将 `/metrics` 暴露至公网。

### GET /health

**用途**：进程存活（liveness）。

**响应**：`200 OK`，body 可为 `{"status":"ok"}`。

### GET /ready

**用途**：依赖就绪（readiness）——PostgreSQL、Redis、对象存储、模型网关可达性等。

**响应**：全部就绪 `200`；任一失败 `503` + 简要原因（不含敏感连接串）。

### GET /metrics

**用途**：Prometheus 抓取；路径可与 Ingress 前缀并存（如 `/metrics` 位于网关根路径）。

**响应**：`text/plain` Prometheus 格式。

---

## 认证接口

### POST /auth/exchange

portal 用现有 JWT 换取 short-lived JWT。

**请求**：

```http
POST /auth/exchange
Authorization: Bearer <portal-JWT>
Content-Type: application/json

{
  "agent_id": "contract-review-agent"
}
```

**响应**：

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_at": 1736000300,
  "agent_id": "contract-review-agent"
}
```

**错误码**：`INVALID_PARAMS`, `FORBIDDEN`（用户无该 Agent 权限）

---

### POST /auth/session

widget 用 short-lived JWT 换 session cookie。

**请求**：

```http
POST /auth/session
Content-Type: application/json

{
  "token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**响应**：Set-Cookie: session_id=...; HttpOnly; Secure; SameSite=Strict

**错误码**：`TOKEN_EXPIRED`, `TOKEN_REUSED`

---

### POST /auth/heartbeat

延长 session cookie 有效期。

**请求**：Cookie: session_id=...

**响应**：200 OK（响应头含 `Set-Cookie` 刷新 max-age）

**协议细节**：
- **前端行为**：widget 每 **5 分钟** 自动发送一次 heartbeat（通过 `setInterval`，仅在页面 `visibilityState === 'visible'` 时触发）
- **后端行为**：收到 heartbeat 后同时刷新三层过期时间：
  1. 数据库 `sessions.expires_at` = now + 30min（权威来源）
  2. Redis `session:{session_id}` TTL 同步延长
  3. 返回 `Set-Cookie` 响应头，刷新浏览器端 cookie max-age
- **心跳失败**：连续 3 次 heartbeat 失败（网络断开或返回 401）→ widget 提示用户"网络异常，会话可能已过期"
- **过期判定**：以数据库 `sessions.expires_at` 为准；Redis TTL 和 cookie max-age 仅作同步参考

---

### GET /auth/me

返回当前 session 的**非敏感**展示字段，供 Chat Widget 顶栏展示（prd.md §4.5.4）。

**请求**：Cookie: session_id=...

**响应** 200：

```json
{
  "user_id_hint": "…a1b2c3",
  "department": "legal",
  "user_id_hash": "a1b2c3d4e5f6...",
  "permissions": ["agent.read", "agent.write"]
}
```

`permissions` 为门户 JWT 兑换写入会话的 ** capability 列表**（可选字段；无则为 `[]`），供 Widget 判断运营台等前端能力（与注册中心 `agent.admin` / `agent.write` 等对齐）。

`user_id_hint` 为 `user_id_hash` 尾部截断，不含明文用户标识。`user_id_hash` 为 **64 位十六进制**的 SHA-256 摘要（与审计/会话表一致），**非明文**；供 Widget 可选 **IndexedDB SubtleCrypto** 本地加密密钥派生（见 [11-chat-widget.md](11-chat-widget.md) 分层存储）。

---

## Agent 用户侧接口

### GET /agents

列出当前用户有权限的 Agent 列表。

**响应**：

```json
{
  "agents": [
    {
      "id": "contract-review-agent",
      "name": "合同审查助手",
      "avatar": "/static/agents/contract.png",
      "description": "...",
      "tags": ["legal", "contract"]
    }
  ]
}
```

---

### GET /agents/{agent_id}

Agent 详情（含 ui_config）。

**响应**：

```json
{
  "id": "contract-review-agent",
  "name": "合同审查助手",
  "ui_config": {
    "title": "合同审查助手",
    "avatar": "/static/agents/contract.png",
    "welcome_message": "...",
    "input_placeholder": "...",
    "quick_actions": [...],
    "attachments": {...}
  }
}
```

---

### POST /agents/{agent_id}/init

初始化会话，触发 Skill Compiler 生成 RunSpec。

**请求体（JSON，均可选）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 续用已有会话时传入 |
| `model` | string | 覆盖本会话主模型：须为 `models.yaml` 中已配置的 **逻辑键** 或 **`model_aliases`** 中的别名 |

**副作用（PRD §10.5）**：成功返回后，服务端写入 **MAU 元数据**（`user_id_hash` + `agent_id` + **自然日** + count），**不含对话内容**。

**响应**：

```json
{
  "session_id": "sess_abc123",
  "run_id": "run_20260507_001",
  "ui_config": {...},
  "runtime_model": "MiniMax-M2.7",
  "available_models": [
    {
      "id": "MiniMax-M2.7",
      "provider": "minimax",
      "endpoint_host": "api.minimaxi.com",
      "api_model": "MiniMax-M2.7",
      "max_tokens": 32768,
      "rpm": 60
    }
  ],
  "model_aliases": { "default": "MiniMax-M2.7", "minimax": "MiniMax-M2.7" },
  "degradation": { "level": 0, "reason": null, "hint": null }
}
```

**错误码**：`AGENT_INACTIVE`, `SKILL_INVALID`、`COMPILE_ERROR`、**`INVALID_MODEL`**（未知或未配置的 `model`）

---

### GET /api/v1/agents/catalog/models

列出平台已配置的 OpenAI 兼容路由（逻辑 id、provider、endpoint 主机摘要、`api_model`、配额字段）。用于 Widget 模型切换 UI。需与 Agent 列表相同的登录态。

---

### POST /agents/{agent_id}/chat

发送消息，SSE 流式返回。

**请求**：

```json
{
  "message": "请审查这份合同",
  "session_id": "sess_abc123",
  "file_ids": ["file_uuid_1", "file_uuid_2"]
}
```

**参数说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | 是 | 用户输入文本 |
| `session_id` | string | 是 | 当前会话 ID |
| `file_ids` | [string] | 否 | 已上传文件的临时 ID 列表（通过 `/upload` 获取），仅在当前 session 内有效 |

**SSE 事件流**：

遵循 HTML SSE：`event:` + `data:` JSON 行；一条逻辑事件可拆多条 `data:`（极少用）。**客户端应以 JSON 内 `type` 字段为主**，`event:` 名称可为 `message` 统一通道。

| `type`（data JSON） | 含义 |
|---------------------|------|
| `text` | 助手文本增量或全文片段（流式拼接） |
| `tool_call` | 工具调用开始/进行中；含 `tool_id`、`call_id`、`status` |
| `tool_result` | 工具返回摘要（可能截断展示）；完整审计在服务端 |
| `degradation` | （可选）当前全局降级等级，供顶栏 Banner |
| `done` | 本轮结束；含 `output` 最终文本、`schema_valid`、`message_id` |
| `error` | 不可恢复错误；含 `code`、`message` |

**示例**：

```
event: message
data: {"type": "text", "delta": "正在审查..."}

event: message
data: {"type": "tool_call", "tool_id": "kb.search", "call_id": "call_1", "status": "running"}

event: message
data: {"type": "tool_result", "tool_id": "kb.search", "call_id": "call_1", "preview": "..."}

event: message
data: {"type": "done", "output": "...", "schema_valid": true, "message_id": "msg_007"}

event: message
data: {"type": "error", "code": "MODEL_UNAVAILABLE", "message": "..."}
```

与 Runner 工具循环细节见 [08-agent-runner.md](08-agent-runner.md)。

---

### POST /agents/{agent_id}/new-session

主动结束当前会话，开启新会话（生成新 RunSpec）。

**请求**：Cookie: session_id=...；可选查询参数 **`?model=<逻辑键或别名>`**（与 `models.yaml` 一致），等价于 `/init` 的 JSON `model` 字段。

**响应**：同 `/init`

---

### POST /agents/{agent_id}/resume

页面刷新后恢复未完成的会话（从 checkpoint 恢复）。

**请求**：

```json
{
  "session_id": "sess_abc123",
  "checkpoint_id": "cp_003"
}
```

**响应**：

```json
{
  "session_id": "sess_abc123",
  "run_id": "run_20260507_001",
  "status": "running",
  "messages": [
    { "role": "user", "content": "请审查这份合同" },
    { "role": "assistant", "content": "正在为您审查..." }
  ],
  "turn_count": 2,
  "ui_config": {...}
}
```

**错误码**：`SESSION_EXPIRED`（>30 分钟无活动，需重新 `/init`）, `RUNSPEC_MISMATCH`

---

### POST /agents/{agent_id}/upload

文件上传（multipart/form-data）。

**请求**：

```http
POST /agents/{agent_id}/upload
Content-Type: multipart/form-data
Cookie: session_id=...

file: <二进制文件>
```

**前端预检**（widget 层）：校验 `ui_config.attachments.accept` 和 `max_size_mb`

**后端二次校验**：重新校验文件类型和大小，防绕过

**存储策略**：
- 敏感文件不写磁盘，直接流入内存缓冲区或直传文档解析服务
- 临时缓冲在会话内存中，关 tab / 会话超时即释放
- 返回临时 `file_id`，仅在当前 session 内有效

**响应**：

```json
{
  "file_id": "file_uuid",
  "name": "合同.docx",
  "size": 10240
}
```

**错误码**：`INVALID_PARAMS`（文件类型/大小不符）

---

### POST /feedback

用户反馈（thumbs up / down + 理由标签 + 文字评论）。

**请求**：

```json
{
  "session_id": "sess_abc123",
  "message_id": "msg_007",
  "agent_id": "contract-review-agent",
  "run_id": "run_20260507_001",
  "feedback": "thumbs_down",
  "reasons": ["inaccurate", "wrong_citation"],
  "comment": "第 3 条引用的制度已于 2025 年废止"
}
```

**约束**：
- `feedback` 必填：`thumbs_up` 或 `thumbs_down`
- `reasons` 可选，仅在 `thumbs_down` 时有效
- `comment` 可选，最多 200 字
- `message_id` 用于精确定位被评价的回复

**响应**：200 OK（异步写入 `feedback_logs` 表）

**错误码**：`INVALID_PARAMS`（缺少必填字段）, `SESSION_NOT_FOUND`

---

## Agent 管理接口（管理员）

### POST /agents

注册新 Agent。

**请求**：完整 agent.yaml JSON 表示

**权限**：`agent.admin`

---

### PUT /agents/{agent_id}

更新 Agent 配置。

**权限**：`agent.write`（owner 或 department_admin） / `agent.admin`

---

### DELETE /agents/{agent_id}

下架 Agent（lifecycle_state → archived）。

**权限**：`agent.admin`

---

### POST /agents/{agent_id}/releases

发布新版本 / 调整灰度策略。

**请求**：

```json
{
  "strategy": "canary",
  "canary": {
    "percent": 10,
    "target_departments": ["legal"]
  }
}
```

**权限**：`agent.admin`

---

### GET /agents/{agent_id}/versions

查看历史版本列表（保留最近 10 个）。

**响应**：

```json
{
  "versions": [
    {"version": "0.1.2", "created_at": "...", "strategy": "full"},
    {"version": "0.1.1", "created_at": "...", "strategy": "canary"}
  ]
}
```

---

## Skill 管理接口（管理员）

详见 [04-skill-package-spec.md](04-skill-package-spec.md) §Skill Registry 接口规范。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/skills` | 注册新 Skill |
| PUT | `/skills/{skill_id}` | 升级 Skill |
| GET | `/skills` | 列出所有 Skill |
| GET | `/skills/{skill_id}` | Skill 详情 |
| DELETE | `/skills/{skill_id}` | 下架 Skill（标记 deprecated，不物理删除，保留历史版本） |

---

## Tool 管理接口（管理员）

详见 [09-tool-gateway.md](09-tool-gateway.md) §Tool Registry 设计。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tools` | 注册新 Tool |
| GET | `/tools` | 列出可用 Tool |
| GET | `/tools/{tool_id}` | Tool 详情 |

---

## 策略管理接口（平台管理员 / 部门管理员）

### GET /policies/platform

列出所有平台级策略（platform_policy）。

**权限**：`platform_admin`（查看全部）；`department_admin`（仅查看，无修改权）

**响应**：

```json
{
  "policies": [
    {
      "id": "platform_base",
      "version": 3,
      "prompt": "你是央企内部智能助手。你的回答必须：...",
      "enabled": true,
      "created_at": "2026-01-15T08:00:00Z",
      "updated_at": "2026-05-01T10:00:00Z"
    }
  ]
}
```

---

### POST /policies/platform

新增平台级策略（version 自动递增）。

**请求**：

```json
{
  "id": "platform_base",
  "prompt": "你是央企内部智能助手。你的回答必须：\n1. 不涉及国家秘密、商业秘密\n2. 不给出法律意见替代专业律师\n...",
  "enabled": true
}
```

**权限**：`platform_admin`

---

### PUT /policies/platform/{policy_id}

更新平台级策略（创建新版本，旧版本保留）。

**请求**：同上（version 字段由系统自动生成，请求中无需传入）

**权限**：`platform_admin`

---

### GET /policies/org/{department}

列出某部门的所有组织策略（org_policy）。

**响应**：

```json
{
  "department": "legal",
  "policies": [
    {
      "id": "legal_policy_v2",
      "version": 2,
      "prompt": "你是法务部智能助手。引用制度时必须标注文号和生效日期。...",
      "enabled": true,
      "created_at": "2026-03-10T09:00:00Z"
    }
  ]
}
```

**权限**：`platform_admin`（查看全部部门）；`department_admin`（仅查看本部门）

---

### POST /policies/org

新增部门策略。

**请求**：

```json
{
  "id": "legal_policy_v2",
  "department": "legal",
  "prompt": "你是法务部智能助手。引用制度时必须标注文号和生效日期。...",
  "enabled": true
}
```

**权限**：`platform_admin`（任意部门）；`department_admin`（仅本部门）

---

### PUT /policies/org/{policy_id}

更新部门策略（创建新版本）。

**权限**：`platform_admin`（任意部门）；`department_admin`（仅本部门）

---

## 审计查询接口（平台管理员 / 审计员）

> **阶段说明**：审计 **写入（minimal）自 P0 起已启用**；本章 REST 为 **查询与报表（消费端）**，工程上多见于 **P0.5+** 管理台交付。详见 [14-roadmap.md](14-roadmap.md)、[47-prd-alignment.md](47-prd-alignment.md)。

### GET /audit/logs

分页查询审计日志。

**查询参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `run_id` | string | 按 RunSpec 过滤 |
| `session_id` | string | 按会话过滤 |
| `agent_id` | string | 按 Agent 过滤 |
| `department` | string | 按部门过滤 |
| `user_id_hash` | string | 按用户 hash 过滤 |
| `level` | enum | minimal / standard / full |
| `start_time` | ISO8601 | 开始时间 |
| `end_time` | ISO8601 | 结束时间 |
| `page` | int | 页码，默认 1 |
| `page_size` | int | 每页条数，默认 20，最大 100 |

**响应**：

```json
{
  "total": 1502,
  "page": 1,
  "page_size": 20,
  "logs": [
    {
      "id": 10001,
      "run_id": "run_20260507_001",
      "session_id": "sess_abc123",
      "timestamp": "2026-05-07T14:30:00Z",
      "level": "minimal",
      "user_id_hash": "sha256_abc...",
      "agent_id": "contract-review-agent",
      "department": "legal",
      "tool_calls": [{"tool_id": "kb.search", "latency_ms": 150}],
      "token_count": 3500,
      "cost": 0.05,
      "error_code": null,
      "retrieval_ids": ["doc_001", "doc_002"]
    }
  ]
}
```

**权限**：`platform_admin`（全平台）；`department_admin`（仅本部门数据）；`auditor`（只读，全平台）

**脱敏规则**：
- `minimal` 级日志：不返回 `full_prompt` / `full_output`
- `standard` 级日志：返回 `prompt_summary`（前 200 字）
- `full` 级日志：返回完整 `full_prompt` / `full_output`（需 `platform_admin` 或 `auditor` 权限）

---

### GET /audit/logs/export

将当前筛选条件下的审计行导出为 **CSV**（UTF-8 BOM，便于 Excel 打开），列与脱敏规则与 `GET /audit/logs` 一致（`tool_calls` / `retrieval_ids` 为 JSON 字符串列）。

**查询参数**：与 `GET /audit/logs` 相同，另增 `limit`（默认 2000，最大 5000）。

**响应**：`Content-Type: text/csv; charset=utf-8`，`Content-Disposition: attachment`。

**权限**：与 `GET /audit/logs` 相同（`ADMIN_API_TOKEN` / 管理 JWT 口径见运维配置）。

---

### GET /audit/stats/daily

按日汇总统计（用于仪表盘）。

**查询参数**：`start_date`, `end_date`, `agent_id`（可选）, `department`（可选）

**响应**：

```json
{
  "dates": [
    {
      "date": "2026-05-06",
      "request_count": 1200,
      "error_count": 15,
      "token_input": 450000,
      "token_output": 180000,
      "p99_latency_ms": 3200,
      "model_distribution": {"qwen3-32b": 70, "qwen3-14b": 25, "qwen3-8b": 5}
    }
  ]
}
```

**权限**：`platform_admin`, `auditor`

---

### GET /audit/stats/daily/export

将 `GET /audit/stats/daily` 同一筛选条件下的 **`daily_stats` 行**导出为 CSV（UTF-8 BOM）。`model_distribution` 列为 JSON 字符串。

**查询参数**：与 `GET /audit/stats/daily` 相同，另增 `limit`（默认 2000，最大 5000）。

**响应**：`text/csv; charset=utf-8`，`Content-Disposition: attachment`。

**权限**：与 `GET /audit/stats/daily` 相同。

---

### GET /audit/sessions/{session_id}/trace

查询某会话的完整执行轨迹（含 checkpoint 序列）。

**响应**：

```json
{
  "session_id": "sess_abc123",
  "run_id": "run_20260507_001",
  "checkpoints": [
    {
      "checkpoint_id": "cp_001",
      "turn_number": 1,
      "timestamp": "2026-05-07T14:25:00Z",
      "token_count": 1200,
      "tool_calls_so_far": [{"tool_id": "doc.extract", "status": "success"}]
    },
    {
      "checkpoint_id": "cp_002",
      "turn_number": 2,
      "timestamp": "2026-05-07T14:30:00Z",
      "token_count": 3500,
      "tool_calls_so_far": [
        {"tool_id": "doc.extract", "status": "success"},
        {"tool_id": "kb.search", "status": "success"}
      ]
    }
  ]
}
```

**权限**：`platform_admin`（全平台）；`department_admin`（仅本部门）；`auditor`（只读，全平台）

---

## 降级运维接口（平台管理员）

### POST /admin/degradation/level

强制启用某级降级。

**请求**：

```json
{
  "level": 3,
  "reason": "模型集群维护",
  "duration_minutes": 60
}
```

### POST /admin/degradation/recover

强制恢复。

### GET /admin/product-metrics/summary

**prd §10.6 / docs/32**：从 `agent_usage_logs`、`sessions`、`agent_apps`、`feedback_logs` 聚合业务指标（不含对话正文）。

**查询参数**：

| 参数 | 必填 | 说明 |
|------|------|------|
| `start_date` | 是 | `YYYY-MM-DD`，统计区间起始（含） |
| `end_date` | 是 | `YYYY-MM-DD`，统计区间结束（含） |
| `mau_window_days` | 否 | 默认 `30`；与 `end_date` 一起定义 **滚动 MAU 窗口**（1–365） |

**响应字段（摘要）**：`dau_by_day`（按日 distinct `user_id_hash`）、`mau_rolling_distinct_users`（窗口内去重用户）、`mau_rolling_window_start`、`new_chat_sessions`、`new_agents_registered`、`feedback`（`thumbs_up` / `thumbs_down`、`satisfaction_rate`、`participation_vs_sessions`）。区间为空时数值为零或 `null`。

**权限**：与 `POST /admin/degradation/*` 相同（`ADMIN_API_TOKEN`；未配置则 503 `ADMIN_DISABLED`）。

### GET /admin/agents

注册中心 **全量** Agent 列表（含 `cold` / `archived`），与门户可见的 `GET /agents` 过滤列表互补，供 **运营台** 生命周期管理使用。

**查询参数**：

| 参数 | 必填 | 说明 |
|------|------|------|
| `lifecycle_state` | 否 | `active` \| `cold` \| `archived`；不传返回全部 |

**响应（摘要）**：`{ "agents": [ { "id", "name", "version", "lifecycle_state", "release_strategy", "updated_at", ... } ] }`（字段以实现为准，与注册中心表一致）。

**权限（会话 RBAC + 运维 Bearer）**：
- **Cookie 会话**：须具备 **`agent.admin`** 或 **`agent.write`**（见 `deps_admin.require_registry_operator`）。
- **自动化**：`Authorization: Bearer <ADMIN_API_TOKEN>`（与注册中心写路径同一令牌口径）。

### PATCH /admin/agents/{agent_id}/lifecycle

切换 Agent **生命周期状态**（PRD：`active` / `cold` / `archived`），与注册中心元数据一致。

**请求**：

```json
{
  "lifecycle_state": "cold"
}
```

**权限**：高于列表接口——会话须具备 **`agent.admin`**，或请求携带 **`ADMIN_API_TOKEN`** Bearer（`require_registry_superuser`）。仅有 `agent.write` 的账号可浏览列表但 **不能** 调用本接口（返回 403）。

### POST /admin/agents/{agent_id}/disable

屏蔽某个 Agent。

**请求**：

```json
{
  "reason": "法务准确性问题",
  "duration_minutes": 30
}
```

---

## 用户与权限管理接口（平台管理员）

### GET /admin/users

查询用户列表（支持分页、按部门过滤）。

**查询参数**：
- `department`（可选）：部门代码
- `page`（可选，默认 1）
- `page_size`（可选，默认 20，最大 100）

**响应**：

```json
{
  "items": [
    {
      "user_id": "u123",
      "name": "张三",
      "department": "legal",
      "roles": ["agent.user", "knowledge.read"],
      "created_at": "2026-01-15T09:00:00Z"
    }
  ],
  "total": 156,
  "page": 1,
  "page_size": 20
}
```

### PUT /admin/users/{user_id}/roles

为用户分配角色。

**请求**：

```json
{
  "roles": ["agent.user", "agent.admin", "knowledge.read"],
  "reason": "担任法务部 Agent 管理员"
}
```

**约束**：
- 不允许为自己修改角色（防权限提升）
- 修改 platform_admin 角色需当前用户也是 platform_admin

### GET /admin/departments

获取部门列表（扁平 + 树形）。

**响应**：

```json
{
  "departments": [
    { "code": "legal", "name": "法务部", "parent": null },
    { "code": "legal-contract", "name": "合同管理组", "parent": "legal" }
  ]
}
```

---

## Token 预算管理接口（平台/部门管理员）

### GET /admin/token-quotas

查询各层级 token 预算及实际用量。

**查询参数**：
- `scope`（可选）：`platform` / `department` / `agent` / `user`
- `scope_id`（可选）
- `period`（可选，格式 `YYYY-MM`）

**响应**：

```json
{
  "items": [
    {
      "scope": "department",
      "scope_id": "legal",
      "budget_tokens": 100000000,
      "used_tokens": 45230000,
      "usage_rate": 0.45,
      "period": "2026-05",
      "period_start": "2026-05-01",
      "period_end": "2026-05-31"
    }
  ]
}
```

### PUT /admin/token-quotas/{scope}/{scope_id}

调整指定层级的 token 预算。

**请求**：

```json
{
  "budget_tokens": 150000000,
  "effective_next_period": false
}
```

**说明**：
- `effective_next_period = false`：立即生效（仅影响当月剩余预算，不改变 `period_start`）
- `effective_next_period = true`：下月生效（创建新周期记录）

---

## 接口对照速查表

| 接口 | 认证 | 权限 | 详见 |
|------|------|------|------|
| `/health` | 无 | 公网应禁止或 ACL | 本文档 + 37-production-checklist.md |
| `/ready` | 无 | 同上 | 本文档 |
| `/metrics` | 无 | **仅内网** Prometheus | 32-observability-design.md |
| `/auth/exchange` | portal-JWT | 任意已登录用户 | 本文档 + 06-api-gateway.md |
| `/auth/session` | short-lived JWT | 任意 | 本文档 + 06-api-gateway.md |
| `/agents` | session cookie | user+ | 本文档 |
| `/agents/{id}/init` | session cookie | user+ | 本文档 |
| `/agents/{id}/chat` | session cookie | user+ | 本文档 |
| `/agents/{id}/upload` | session cookie | user+ | 本文档 |
| `/agents/{id}/resume` | session cookie | user+ | 本文档 + 08-agent-runner.md |
| `/feedback` | session cookie | user+ | 本文档 + 11-chat-widget.md |
| `/agents` (POST) | admin JWT | agent.admin | 本文档 + 03-agent-app-spec.md |
| `/agents/{id}/releases` | admin JWT | agent.admin | 本文档 + 14-roadmap.md |
| `/skills/*` | admin JWT | skill.publish | 本文档 + 04-skill-package-spec.md |
| `/tools/*` | admin JWT | tool.admin | 本文档 + 09-tool-gateway.md |
| `/policies/*` | admin JWT | platform_admin / department_admin | 本文档 + 07-skill-compiler.md |
| `/audit/*` | admin JWT | platform_admin / auditor | 本文档 + 12-security-audit.md |
| `/admin/degradation/*` | admin JWT | platform_admin | 本文档 + 13-concurrency.md |
| `/admin/product-metrics/summary` | `ADMIN_API_TOKEN`（Bearer） | 运维 / platform_admin（与降级接口同令牌口径） | 本文档 + [32-observability-design.md](32-observability-design.md) |
| `/admin/agents` | session cookie 或 `ADMIN_API_TOKEN`（Bearer） | `agent.admin` / `agent.write`（会话）或 Bearer | 本文档 |
| `/admin/agents/{id}/lifecycle` | session cookie 或 `ADMIN_API_TOKEN`（Bearer） | **`agent.admin`**（会话）或 Bearer（`agent.write` 不足） | 本文档 |
| `/admin/agents/{id}/disable` | admin JWT | platform_admin | 本文档 + 03-agent-app-spec.md |
| `/admin/users` | admin JWT | platform_admin | 本文档 |
| `/admin/users/{id}/roles` | admin JWT | platform_admin | 本文档 |
| `/admin/departments` | admin JWT | platform_admin / department_admin | 本文档 |
| `/admin/token-quotas` | admin JWT | platform_admin / department_admin | 本文档 + 10-model-gateway.md |

---

## 前端可观测性接口

### POST /metrics/frontend

widget 通过 `navigator.sendBeacon` 上报前端性能与体验指标。

**请求**：

```http
POST /api/v1/metrics/frontend
Content-Type: application/json

{
  "name": "af_widget_lcp_seconds",
  "value": 1.2,
  "labels": {
    "agent_id": "contract-review-agent"
  },
  "timestamp": 1744000000000
}
```

**约束**：
- `name` 必须以 `af_widget_` 前缀开头
- `value` 为 float64
- `labels` 中不可包含 `user_id`、`token` 等敏感字段
- 服务端仅做聚合写入 Prometheus，不做明细存储

**响应**：202 Accepted（sendBeacon 不要求读取响应体）

---

## 进程内调用（非 HTTP 对外契约）

下列调用存在于 **Agent Runner ↔ Tool Gateway ↔ 模型网关** 之间，**不**对浏览器或 portal 暴露，仅供实现对照 PRD §8：

| 调用方 | 接收方 | 说明 |
|--------|--------|------|
| Runner | Tool Gateway | 同步或异步执行 `kb.search` / `doc.extract` / 内部 API 等（见 [09-tool-gateway.md](09-tool-gateway.md)） |
| Runner | Model Gateway | OpenAI 兼容 Chat Completion / stream |
| Tool Gateway | 知识服务 / Doc Worker | HTTP 或队列回调；RAG **不作为本仓库 REST 出口**（PRD §2） |

对外 REST **唯一入口**仍以本文档 HTTP 表为准。

---

## OpenAPI / SDK

- 推荐在 CI 中由 FastAPI **自动生成** `openapi.json`，再固化 **`docs/openapi/agent-factory-v1.yaml`**（或通过 Redocly 转换）。
- 前端 TypeScript 类型可由 `openapi-typescript` 从同一 YAML 生成，与 `widget/src/types/api.ts` 对齐。
- **版本策略**：URL 前缀 `/api/v1` 与 RunSpec `runspec_schema_version` 独立；破坏性 HTTP 变更通过新版本前缀 `/api/v2` 发布。
