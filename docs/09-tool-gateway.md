# 09. Tool Gateway 设计

> 版本：v0.6 · 2026-05-06

---

## 一句话职责

工具注册、权限校验、审计、超时、熔断。

**类比**：楼里每个工具室门口的安检门——检查你有没有权限进、你带的材料对不对、超时了自动关门、出问题自动封锁。

---

## 核心原则

**权限校验落在系统层（不是 prompt 层）**。prompt 里写"你不能用这个工具"是**不可靠的**——模型可能忘、可能被绕过。**真正的权限必须在 Tool Gateway 硬校验**。

每次工具调用都校验：

- 调用者身份
- Agent ID
- RunSpec ID
- 工具权限
- 输入参数合法性
- 数据域权限
- 超时和频率

---

## Tool Registry 设计

**Tool 是平台级资源**——不属于某个 Skill / 某个 Agent，是平台共享的能力池。

### 注册接口（仅平台管理员可写）

```
POST   /api/v1/tools      # 注册新 Tool（管理员）
GET    /api/v1/tools      # 列出可用 Tool
GET    /api/v1/tools/<tool_id>   # Tool 详情
```

### 每个 Tool 必含

```yaml
id: kb.search
version: 1.0.0
input_schema: schemas/kb_search_input.json
output_schema: schemas/kb_search_output.json
permission_required:        # 哪些角色 / 部门能调
  - knowledge.read
timeout_seconds: 10
rate_limit:
  per_user: 60/min
  global: 1000/min
implementation:             # 后端怎么实现
  type: http_api            # http_api / controlled_script
  endpoint: https://kb.internal/search
```

**为什么 Tool 不像 Skill 那样允许业务部门自由新增**：Tool 是权限层基础设施，新增 Tool = 扩大攻击面。新增必须走**双签审批 + 安全评审**。

**业务部门有新工具需求** → 找平台团队提需求 → 平台团队评估 + 实现 + 注册。这一步不能简化。

---

## 工具调用流程

```
Agent Runner 调用 Tool Gateway
  ↓
1. 身份校验
   ├─→ 检查 run_id 是否存在且活跃
   ├─→ 检查 tool_id 是否在 RunSpec.allowed_tools 中
   └─→ 检查 user 是否有调用该 tool 的权限
  ↓
2. 参数校验
   ├─→ 用 Tool Registry input_schema 校验 params
   └─→ 检查数据域参数是否在 RunSpec.retrieval_scopes 中
  ↓
3. 限流检查
   ├─→ per_user 限流
   ├─→ per_agent 限流
   └─→ global 限流
  ↓
4. 熔断检查
   ├─→ 该 Tool 是否被手动下线
   └─→ 该 Tool 最近错误率是否超过阈值
  ↓
5. 执行工具
   ├─→ http_api 类型：发 HTTP 请求
   ├─→ controlled_script 类型：投递到 Worker 队列
   └─→ 内部函数类型：直接调用
  ↓
6. 记录审计日志
   ├─→ tool_id
   ├─→ params（脱敏后）
   ├─→ latency
   ├─→ status
   └─→ error（如有）
  ↓
7. 返回结果给 Runner
```

---

## 权限校验详细规则

### 第一层：RunSpec 白名单

```python
if tool_id not in run_spec.allowed_tools:
    raise PermissionDenied(f"Tool {tool_id} not in RunSpec allowed_tools")
```

### 第二层：用户权限

```python
required = tool_registry[tool_id].permission_required
if not all(p in user.permissions for p in required):
    raise PermissionDenied(f"User lacks permission for {tool_id}")
```

### 第三层：数据域权限

```python
if tool_id == "kb.search":
    requested_scope = params.get("scope")
    if requested_scope not in run_spec.retrieval_scopes:
        raise PermissionDenied(f"Data domain {requested_scope} not allowed")
```

### 第四层：Tool Gateway 策略

```python
if tool_gateway.is_disabled(tool_id):
    raise ToolUnavailable(f"Tool {tool_id} is temporarily disabled")
```

---

## 限流策略

| 维度 | 默认配额 | 说明 |
|------|---------|------|
| per_user | 60/min | 单个用户调用频率 |
| per_agent | 500/min | 单个 Agent 调用频率 |
| global | 1000/min | 全平台调用频率 |
| per_department | 300/min | 单个部门调用频率 |

超限响应：429 Too Many Requests，带 `Retry-After` header。

---

## 熔断机制

| 指标 | 阈值 | 动作 |
|------|------|------|
| 错误率 | > 10%（1 分钟内） | 打开熔断，拒绝新请求 |
| 慢请求 | P99 > 5s（1 分钟内） | 半开熔断，部分放行 |

恢复：

- 熔断打开后 30 秒进入半开状态
- 半开状态放少量请求试探
- 连续 5 个成功 → 完全关闭
- 任一失败 → 重新打开

---

## 限流算法详细设计

### 算法选择：滑动窗口计数器（Redis Sorted Set）

| 维度 | 算法 | 说明 |
|------|------|------|
| per_user / per_agent / per_dept | 滑动窗口 | 精确统计 60 秒内请求数，误差 < 1 个请求 |
| global | 令牌桶（近似） | Redis INCR + EXPIRE，允许瞬间突发 10% |

### Redis 数据结构

```
# 滑动窗口（ZSet）：score = 时间戳（秒），member = 请求唯一 ID
ratelimit:user:{user_id}:{tool_id}  ->  ZSet
ratelimit:agent:{agent_id}:{tool_id} ->  ZSet
ratelimit:dept:{dept}:{tool_id}      ->  ZSet

# 令牌桶（String）：value = 当前剩余令牌数
ratelimit:global:{tool_id}           ->  String
```

### 滑动窗口原子操作（Lua 脚本）

```lua
-- 伪代码：检查用户是否超限
local key = KEYS[1]
local window = tonumber(ARGV[1])      -- 60 秒
local limit = tonumber(ARGV[2])       -- 配额（如 60）
local now = tonumber(ARGV[3])         -- 当前时间戳
local member = ARGV[4]                -- 请求唯一 ID

-- 1. 清理过期窗口
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- 2. 统计当前窗口内数量
local current = redis.call('ZCARD', key)

if current >= limit then
    return {0, current}  -- 拒绝
end

-- 3. 记录本次请求
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 1)
return {1, current + 1}  -- 通过
```

**为什么用 Lua**：`ZREMRANGEBYSCORE + ZCARD + ZADD` 三条命令必须在 Redis 端原子执行，防止并发竞态。

### 超限响应

```json
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/json

{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Tool kb.search per_user limit exceeded: 60/min",
    "retry_after": 30,
    "request_id": "req_abc123"
  }
}
```

---

## read_reference 工具（Skill 按需加载）

Tool Gateway 提供一个特殊工具 `read_reference`，用于模型在循环中按需拉取 references/ 中的内容。该工具属于**系统内置工具**，权限校验逻辑与其他工具不同：

```json
{
  "tool_calls": [{
    "function": {
      "name": "read_reference",
      "arguments": "{\"name\": \"checklist\"}"
    }
  }]
}
```

Tool Gateway 处理：

1. 检查 `name` 是否在 RunSpec.lazy_references 白名单中
2. **权限校验**：`read_reference` 不校验用户角色权限（`permission_required` 不生效），仅校验：
   - 当前 `run_id` 是否活跃
   - 请求读取的 `name` 是否在 RunSpec.lazy_references 列表内
   - 如不在列表内 → 拒绝并返回 `"Reference not in RunSpec lazy_references"`
3. 从 Skill Registry 拉取该版本的 reference 文件
4. 校验文件 hash 与 RunSpec.skill_file_manifest['references/{name}.md'] 一致
5. 返回内容给模型

不匹配 → 报错 "Skill 包版本不一致"，会话异常终止。

**为什么 read_reference 不校验用户权限**：该工具是 Agent Runner 执行循环的基础设施，用户已经通过 `/init` 获得了该 Agent 的会话权限，RunSpec.lazy_references 白名单本身就是最细粒度的权限控制。再叠加 RBAC 会导致普通用户无法运行任何需要按需加载 reference 的 Agent。

---

## 工具类型矩阵

| 类型 | 实现方式 | 示例 | 安全级别 |
|------|---------|------|---------|
| http_api | HTTP 请求到外部服务 | kb.search | 中（需校验 endpoint） |
| controlled_script | 投递到受控 Worker 池 | normalize_contract_text | 高（沙箱执行） |
| internal_function | 直接调用内部函数 | doc.extract | 中（需审计） |
| mcp | Model Context Protocol 适配器 | 外部 MCP Server | 中（需白名单 + 审计） |

---

## MCP 工具接入

> 本章节扩展自 PRD §13.3 对 nanobot MCP 接入方式的借鉴，作为 P1+ 阶段的外部工具标准化接入方案。

### 为什么需要 MCP

**MCP（Model Context Protocol）** 是 Anthropic 推出的开放标准，用于统一模型与外部工具/数据源的交互方式。企业内网未来可能有：

- 第三方系统提供的 MCP Server（如 OA 系统、ERP 系统）
- 内部团队按 MCP 标准封装的新能力

本系统不直接暴露 MCP 接口给模型，而是**通过 Tool Gateway 将 MCP Server 映射为内部 Tool**，保持权限校验和审计的统一性。

### 注册方式

```yaml
id: oa.leave_query
version: 1.0.0
name: 请假记录查询
input_schema: schemas/oa_leave_input.json
output_schema: schemas/oa_leave_output.json
permission_required:
  - oa.read

implementation:
  type: mcp                          # 新增类型
  mcp_server_id: oa-mcp-server       # MCP Server 标识
  mcp_tool_name: query_leave_records # MCP Server 暴露的工具名
  endpoint: http://oa-mcp.internal:8080/sse  # MCP Server SSE 端点
  timeout_seconds: 15
```

### 调用流程

```
Agent Runner 调用 Tool Gateway
  ↓
Tool Gateway 识别 implementation.type = mcp
  ↓
校验权限（同其他工具：RunSpec 白名单 + 用户权限 + Gateway 策略）
  ↓
通过 MCP 客户端连接到 MCP Server（SSE 或 stdio 传输）
  ↓
调用 mcp_tool_name，传入参数
  ↓
等待 MCP Server 返回
  ↓
结果格式化后返回给 Runner
  ↓
记录审计日志（tool_id = oa.leave_query，保留 MCP 原始调用信息）
```

### 安全边界

| 约束 | 说明 |
|------|------|
| **白名单准入** | MCP Server 必须预先在平台注册，不允许模型动态发现 |
| **网络隔离** | MCP Server 必须在白名单内网段，不允许访问外网 |
| **参数校验** | 通过 Tool Registry input_schema 校验，不依赖 MCP Server 自我校验 |
| **审计穿透** | 审计日志记录 MCP Server ID + 工具名 + 参数摘要，与内部工具统一格式 |
| **超时熔断** | MCP Server 响应超时按 Tool Gateway 统一熔断策略处理 |

### 与 nanobot MCP 接入的对齐

nanobot 支持 MCP 工具直接接入。本系统的映射策略：

- **保留**：MCP 工具的发现格式、参数传递方式、结果解析逻辑
- **增加**：Tool Gateway 的权限硬校验层、审计层、熔断层
- **替换**：nanobot 的本地 MCP 连接替换为内网 MCP Server 连接（SSE / HTTP）

---

## 内置工具 Schema

P0 阶段系统提供以下内置工具，其 input_schema 和 output_schema 定义如下。所有内置工具在 Tool Registry 中预注册，无需管理员手动添加。

### `kb.search`

**input_schema**：

```json
{
  "type": "object",
  "properties": {
    "query": { "type": "string", "description": "检索 query" },
    "scope": { "type": "string", "description": "知识域 scope，必须在 RunSpec.retrieval_scopes 内" },
    "top_k": { "type": "integer", "default": 10, "minimum": 1, "maximum": 50 }
  },
  "required": ["query", "scope"]
}
```

**output_schema**：

```json
{
  "type": "object",
  "properties": {
    "results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "doc_id": { "type": "string" },
          "title": { "type": "string" },
          "snippet": { "type": "string" },
          "score": { "type": "number" }
        }
      }
    },
    "total": { "type": "integer" }
  }
}
```

### `doc.extract`

**input_schema**：

```json
{
  "type": "object",
  "properties": {
    "file_id": { "type": "string", "description": "通过 /upload 接口获得的临时文件 ID" },
    "format": { "type": "string", "enum": ["text", "markdown"], "default": "text" }
  },
  "required": ["file_id"]
}
```

**output_schema**：

```json
{
  "type": "object",
  "properties": {
    "content": { "type": "string", "description": "提取的文本内容" },
    "pages": { "type": "integer", "description": "页数（如有）" },
    "status": { "type": "string", "enum": ["success", "partial", "error"] },
    "error_message": { "type": "string" }
  }
}
```

### `read_reference`

**input_schema**：

```json
{
  "type": "object",
  "properties": {
    "name": { "type": "string", "description": "reference 文件名（不含路径和扩展名），必须在 RunSpec.lazy_references 白名单内" }
  },
  "required": ["name"]
}
```

**output_schema**：

```json
{
  "type": "object",
  "properties": {
    "name": { "type": "string" },
    "content": { "type": "string", "description": "reference 文件全文" },
    "hash_match": { "type": "boolean", "description": "是否与 RunSpec.skill_file_manifest 中记录的 hash 一致" }
  }
}
```

**权限说明**：`read_reference` 不校验用户 RBAC 权限，仅校验 `run_id` 活跃且 `name` 在 `RunSpec.lazy_references` 列表内。详见 [08-agent-runner.md](08-agent-runner.md) §Schema 校验。

