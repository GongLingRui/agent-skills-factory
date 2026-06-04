# 06. API 网关与 SSO

> 版本：v0.6 · 2026-05-06

---

## 模块职责

API 网关是系统的**唯一入口**，负责：

- 认证（JWT 验签）
- 识别用户所属部门
- 基础限流（IP / 用户 / 全局）
- 路由到 Agent App 注册中心
- 不处理业务逻辑，只负责"谁能进"
- **CORS 跨域控制**：`ALLOWED_ORIGINS` 必须包含 portal 域名（用户从 portal 点击跳转时 origin 为 portal 地址），否则 widget 无法完成 `/auth/exchange` 和后续 API 调用

**类比**：公司大门保安——查工牌、看部门、控制人流，但不进办公室管业务。

---

## SSO / JWT 短令牌交换（portal 集成）

跟现有 portal 集成的标准流程。**前提**：portal 已用 JWT 做 SSO，agent factory 复用 portal 的认证体系，不重新做登录。

### 流程图

```
portal（用户已用 portal-JWT 登录）
↓ 用户点击"合同审查助手"
↓ POST /auth/exchange
↓ Header: Authorization: Bearer <portal-JWT>
↓ Body: { agent_id: "contract-review-agent" }
agent factory
↓ 验证 portal-JWT 签名 + 过期 + 用户身份
↓ 检查用户对该 agent_id 是否有权限
↓ 签发 short-lived JWT（5 分钟有效，scope = single agent run session）
↓
portal 拿到 short-lived JWT
↓
window.open(`https://agent.company.com/apps/<agent_id>?token=<JWT>`)
widget
↓ 取 token → 验签 → 建 session → 立即从 URL 移除 token
↓ 后续 API 调用走 session cookie 或 Authorization header
```

### 为什么短令牌交换而不是直接传 portal-JWT

- portal-JWT 一般生命周期长（小时级），泄漏代价大
- short-lived JWT 5 分钟过期，绑定单个 agent + 单次会话，泄漏影响极小
- portal-JWT 的 claim 可能不直接含 agent factory 需要的 scope；交换时按规则重新组装
- 央企合规审计能区分"portal 认证事件"和"agent 调用事件"——双层留痕

### short-lived JWT 内容

```json
{
  "sub": "u123",
  "department": "legal",
  "agent_id": "contract-review-agent",
  "scope": "agent.run",
  "permissions": ["kb.search", "doc.extract"],
  "iat": 1736000000,
  "exp": 1736000300,
  "jti": "session-abc123"
}
```

### 实现要点

- portal-JWT 验签密钥跟 agent factory 共享（或 agent factory 通过 JWKS endpoint 拉取 portal 公钥）
- short-lived JWT 用 agent factory 自己的私钥签发
- 单个 jti 只能使用一次（防重放）：widget 第一次调 API 时 agent factory 把 jti 标记为已用，签发 session cookie
- 后续 API 调用走 session cookie，不再用 short-lived JWT
- session cookie 默认有效期 30 分钟，可由 widget 心跳延长
- session cookie **不绑定 agent_id**——这样支持 [Chat Widget 顶栏 Agent 切换](11-chat-widget.md)（不重换 token）
- **会话过期权威来源**：以数据库 `sessions.expires_at` 字段为准，cookie max-age 和 Redis TTL 与之同步，但服务端最终校验以数据库为准

### portal 团队需要做的事

只有两件，工程量极小：

1. 在应用启动器里把"合同审查助手"按钮的点击行为，从原来的 window.open(dify_url) 改成：
   - 调 agent factory 的 /auth/exchange 接口
   - 拿到返回的 short-lived JWT
   - window.open('https://agent.company.com/apps/contract-review-agent?token=<JWT>', '_blank')
2. 调用 /auth/exchange 时把现有的 portal-JWT 放在 Authorization header

预计 **1-2 天工作量**。

---

## 标准 URL 模式

```
https://agent.company.com/apps/<agent_id>?token=<short-lived-JWT>
```

token 是 **5 分钟有效**的一次性令牌，widget 加载后立即从 URL 移除（防历史记录泄露）。

---

## 用户完整路径

1. 用户在 portal 点击"合同审查助手"
2. portal 后端：用现有 portal-JWT 调 /auth/exchange 接口
   → 换一个 **5 分钟有效**的 short-lived JWT
   → JWT 绑定 agent_id + user_id + 部门 + 权限
3. portal 前端：window.open(URL, '_blank')
4. widget 加载 → 从 URL 取 token → 验签 → 建立 session
   → **立刻从 URL 删除 token**（防历史记录泄露）
   → 用 session cookie 调 API
5. 用户对话，widget 把历史存 localStorage
6. 用户关 tab，session 失效，下次重新换新 token

---

## 接口清单

### 认证相关

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/exchange` | portal 换 short-lived JWT |
| POST | `/auth/session` | widget 用 token 换 session cookie |
| POST | `/auth/heartbeat` | 延长 session cookie |

### Agent 相关（用户侧）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/agents` | 列出当前用户有权限的 Agent |
| GET | `/api/v1/agents/<agent_id>` | Agent 详情 |
| POST | `/api/v1/agents/<agent_id>/init` | 初始化会话（编译 RunSpec） |
| POST | `/api/v1/agents/<agent_id>/chat` | 发送消息（SSE 返回） |
| POST | `/api/v1/agents/<agent_id>/new-session` | 开新会话 |
| POST | `/api/v1/agents/<agent_id>/upload` | 文件上传（multipart/form-data） |

### Agent 管理（管理员）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/agents` | 注册新 Agent |
| PUT | `/api/v1/agents/<agent_id>` | 更新 Agent 配置 |
| DELETE | `/api/v1/agents/<agent_id>` | 下架 Agent |
| POST | `/api/v1/agents/<agent_id>/releases` | 发布新版本 / 灰度控制 |
| GET | `/api/v1/agents/<agent_id>/versions` | 查看历史版本（保留最近 10 个） |

### Skill 相关（管理员）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/skills` | 注册新 Skill |
| PUT | `/api/v1/skills/<skill_id>` | 升级 Skill |
| GET | `/api/v1/skills` | 列出所有 Skill |
| GET | `/api/v1/skills/<skill_id>` | Skill 详情 |
| DELETE | `/api/v1/skills/<skill_id>` | 下架 Skill |

### Tool 相关（管理员）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/tools` | 注册新 Tool |
| GET | `/api/v1/tools` | 列出可用 Tool |
| GET | `/api/v1/tools/<tool_id>` | Tool 详情 |

---

## 接口详细规范

### 统一错误码

| HTTP 码 | 业务子码 | 说明 |
|---------|---------|------|
| 400 | `INVALID_PARAMS` | 参数校验失败 |
| 400 | `NO_TOOLS_AVAILABLE` | 权限交集为空，无可用工具 |
| 403 | `AGENT_INACTIVE` | Agent 未激活或已归档 |
| 403 | `FORBIDDEN` | 用户无权限访问该 Agent |
| 429 | `RATE_LIMITED` | 触发限流，带 `Retry-After` header |
| 500 | `SKILL_INVALID` | Skill Package schema 校验失败 |
| 500 | `RUNSPEC_VERSION_UNSUPPORTED` | RunSpec schema 版本不兼容 |

### `/auth/exchange` 返回格式

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_at": 1736000300,
  "agent_id": "contract-review-agent"
}
```

### `/agents/<id>/init` 返回格式

```json
{
  "session_id": "sess_abc123",
  "run_id": "run_20260507_001",
  "ui_config": {
    "title": "合同审查助手",
    "avatar": "/static/agents/contract.png",
    "welcome_message": "...",
    "quick_actions": [...]
  }
}
```

### `/agents/<id>/chat` SSE 事件协议

```
event: message
data: {"type": "text", "content": "正在审查..."}

event: tool_call
data: {"tool_id": "kb.search", "status": "running"}

event: tool_result
data: {"tool_id": "kb.search", "result": "..."}

event: done
data: {"type": "complete", "output": "...", "schema_valid": true}

event: error
data: {"code": "TIMEOUT", "message": "模型响应超时"}
```

### 文件上传 `/agents/<id>/upload`

- **请求**：`multipart/form-data`，字段名 `file`
- **前端预检**：widget 先校验 `ui_config.attachments.accept` 和 `max_size_mb`
- **后端二次校验**：重新校验文件类型和大小，防绕过
- **存储策略**：
  - 敏感文件（合同/公文）**不写磁盘**，直接流入内存缓冲区或直传文档解析服务
  - 临时缓冲在会话内存中，关 tab / 会话超时即释放
  - 返回临时 `file_id`（UUID），仅在当前 session 内有效
- **响应**：`{ file_id: "uuid", name: "合同.docx", size: 10240 }`

---

## widget 安全 Mitigations

详见 [12-security-audit.md](12-security-audit.md) §widget 安全 Mitigations。本节仅列关键要点：

- widget 加载后**立即从 URL 删除 token**
- Referrer-Policy: no-referrer + CSP 严格模式 + HTTPS only + HSTS
- token 一次性 jti + 禁用第三方 SDK + 后端日志 mask token

---

## API Middleware 链顺序与短路契约

请求进入后的中间件执行顺序（从上到下，短路即终止后续处理）：

```
┌─────────────────────────────────────────────┐
│  1. Request ID Middleware                   │  ← 生成/接收 trace_id，注入上下文
│     ↓ 不短路                                 │
│  2. CORS Middleware                           │  ← 跨域预检（OPTIONS 请求在此短路返回 204）
│     ↓ 非 OPTIONS 继续                         │
│  3. Security Headers Middleware             │  ← 注入 HSTS / CSP / Referrer-Policy
│     ↓ 不短路                                 │
│  4. IP Rate Limit Middleware                │  ← 单 IP 限流（超限短路返回 429）
│     ↓ 未超限继续                             │
│  5. Logging Middleware                        │  ← 记录请求元数据（URL mask token）
│     ↓ 不短路                                 │
│  6. Auth Middleware                           │  ← JWT / session cookie 验签
│     ↓ 认证失败短路返回 401                   │
│  7. Global Rate Limit Middleware            │  ← 全局限流（超限短路返回 429）
│     ↓ 未超限继续                             │
│  8. Router / Business Handler               │  ← 业务逻辑
└─────────────────────────────────────────────┘
```

**关键原则**：
- **越早越轻**：认证前的中间件不做 DB 查询（CORS、IP 限流、安全头都基于内存/Redis）
- **短路即返回**：一旦触发限流或认证失败，直接返回，不进入后续中间件
- **响应头全链注入**：Security Headers Middleware 在所有响应路径（含短路响应）中生效

### CORS 与 iframe 嵌入安全详细配置

| 配置项 | 值 | 说明 |
|--------|------|------|
| `ALLOWED_ORIGINS` | `https://portal.company.com,https://agent.company.com` | 精确枚举，禁止 `*` |
| `Access-Control-Allow-Credentials` | `true` | 允许携带 session cookie |
| `Access-Control-Allow-Methods` | `GET, POST, PUT, DELETE, OPTIONS` | |
| `Access-Control-Allow-Headers` | `Content-Type, Authorization, X-Trace-Id` | |
| `Access-Control-Max-Age` | `86400` | 预检结果缓存 24h |

**iframe 场景拒绝**：widget 是独立子站，不通过 iframe 嵌入 portal。若检测到请求头 `Sec-Fetch-Dest: iframe`，返回 `X-Frame-Options: DENY` 和 `Content-Security-Policy: frame-ancestors 'none'`。

---

JWT 在 URL 里虽然 5 分钟过期 + 一次性，但仍存在 5 个泄露面：

- 浏览器历史
- 公司代理 / 防火墙日志
- HTTP Referer header
- 第三方分析脚本
- 截图分享

**Mitigations 清单（每条都不可省）**：

| 措施 | 防什么 |
|------|--------|
| widget 加载后**立即从 URL 删除 token** | 浏览器历史泄露 |
| Referrer-Policy: no-referrer | Referer header 泄露 |
| CSP（Content Security Policy）严格模式 | 第三方脚本注入 |
| HTTPS only + HSTS | 网络嗅探 |
| token 一次性 jti | 重放攻击 |
| widget 禁用第三方 SDK（GA / 字节跳动 SDK 等全禁） | 数据外泄 |
| 后端日志 access log 自动 mask URL 中的 token 参数 | 日志取证泄露 |
