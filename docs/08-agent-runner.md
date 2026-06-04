# 08. Agent Runner 设计

> 版本：v0.6 · 2026-05-06

---

## 一句话职责

执行工具调用循环和轻量编排。

**类比**：流水线工人——手里攥着"出厂订单"（RunSpec），按订单步骤一步步干：问模型、调工具、等结果、再问模型……直到完成。

---

## 工具调用循环（ReAct 简化版）

```
输入：RunSpec + 用户输入 + 历史消息
  ↓
1. 组装 prompt
   ├─→ RunSpec.prompt_parts（系统指令）
   ├─→ 历史消息（多轮上下文）
   └─→ 本次用户输入
  ↓
2. 调模型（经模型网关）
  ↓
3. 解析模型输出
   ├─→ 如果是最终回答 → 进 schema 校验 → 返回给用户
   └─→ 如果是工具调用 → 进步骤 4
  ↓
4. Tool Gateway 执行工具
   ├─→ 权限校验（RunSpec.allowed_tools 白名单）
   ├─→ 参数校验（Tool Registry input_schema）
   ├─→ 执行工具
   └─→ 返回结果
  ↓
5. 工具结果追加到上下文
  ↓
6. 回到步骤 2（下一轮）
  ↓
循环直到：
  - 模型给出最终回答
  - max_turns 达到上限
  - 超时
  - 错误率过高
```

---

## 核心约束

- **Runner 是"纯执行器"**——所有判断在 Skill Compiler 阶段已完成，Runner 只按 RunSpec 字面执行
- **不重新查 RBAC**——Runner 层面不回头查用户角色权限，但 Tool Gateway 会在每次调用时做实时权限 / 限流 / 工具状态校验，以 RunSpec 上界 ∩ 当前最新策略为准（以更小能力为准）。详见 [09-tool-gateway.md](09-tool-gateway.md) §权限校验详细规则
- **RunSpec 不可变**——会话中途 RunSpec 的 prompt 拼装层（agent_instruction / skill_instruction / always references）不会被修改，保证版本一致和可复现

---

## 多轮上下文管理

### 上下文组成

```
System Prompt（RunSpec.prompt_parts）
  ↓
历史消息（用户 + 助手，多轮）
  ↓
工具调用记录（Tool Call + Tool Result）
  ↓
本次用户输入
```

### 上下文治理

当上下文接近 token 上限时，采用以下策略（优先级从高到低）：

1. **history snip**：丢弃最早的历史消息（保留系统 prompt 和最近 N 轮）
2. **tool result budget**：限制单条工具结果长度（超长结果自动摘要）
3. **microcompact**：对过长的工具结果做压缩摘要
4. **提前提示**：widget 显示"对话即将达到上限，建议开新会话"

**推荐默认参数**：

| 策略 | 参数 | 默认值 | 说明 |
|------|------|--------|------|
| history snip | 保留最近轮数 | 4 轮 | 保留系统 prompt + 最近 4 轮（用户+助手） |
| history snip | 最小保留轮数 | 1 轮 | 至少保留最近 1 轮，避免丢完上下文 |
| tool result budget | 最大长度 | 2000 tokens | 单条工具结果超过则自动摘要 |
| tool result budget | 摘要方式 | 提取前 500 tokens + 后 500 tokens + "...（中间省略）..." | 保留头尾，中间省略 |
| microcompact | 触发阈值 | 4000 tokens | 工具结果超过此值才做压缩 |
| microcompact | 压缩方式 | LLM 调用轻量模型（qwen3-8b）生成 300 字摘要 | 不破坏关键信息 |
| 提前提示 | 触发阈值 | 达到模型上下文窗口的 80% | 预留 20% 给下一轮输出 |

**Runner 实现（P0）**：在 ``RunSpec.runtime["context_memory"]`` 中配置（由 ``agent.yaml`` 的 ``limits.context_memory`` 经 Compiler 写入）。采用**字符量近似 token**（无分词器依赖）。**默认 ``compression=summarize``**：超长时调用模型将较早对话压成一条「本会话摘要」用户消息，再拼接最近若干轮原文，**避免破坏性 snip**；仅在摘要失败时回退 ``snip``。超长 **tool** 默认 ``tool_compression=summarize``（模型压要点）；可设 ``truncate`` 回退为头尾省略。**跨会话**：表 ``user_agent_memory``（``user_id_hash`` + ``agent_id``）存滚动「记忆卡」，每轮助手落 checkpoint 后增量合并；新会话在系统提示末尾注入 ``## 跨会话记忆（自动摘要）``。**checkpoint 中的 ``messages`` 仍为完整对话**，仅模型侧压缩。

| 字段 | 类型 | 默认 | 含义 |
|------|------|------|------|
| ``enabled`` | bool | true | 关闭则不做压缩/跨会话注入 |
| ``compression`` | str | summarize | ``summarize``（模型摘要）或 ``snip``（丢弃最早轮） |
| ``cross_session_memory_enabled`` | bool | true | 是否读写 ``user_agent_memory`` 并在系统提示注入 |
| ``keep_recent_user_turns`` | int | 4 | 摘要后保留的最近用户轮数（verbatim 尾巴） |
| ``min_user_turns`` | int | 1 | 与上项共同约束下限 |
| ``history_budget_chars`` | int | 96000 | 超过则触发摘要（或 snip）循环，可多轮直至低于预算或达 ``max_shrink_rounds`` |
| ``summary_max_output_tokens`` | int | 1200 | 单次会话摘要 / 跨会话合并的产出上限 |
| ``summarization_model`` | str | null | 空则与主对话模型相同 |
| ``summarize_input_cap_chars`` | int | 28000 | 送入摘要模型的线性化输入上限 |
| ``max_shrink_rounds`` | int | 2 | 每用户回合内最多压缩轮数 |
| ``tool_compression`` | str | summarize | ``summarize`` 或 ``truncate`` |
| ``tool_result_max_tokens`` | int | 2000 | 工具 JSON 超过则触发摘要或截断 |
| ``tool_result_head_tokens`` / ``tool_result_tail_tokens`` | int | 各 500 | 仅 ``truncate`` 时头尾保留量 |
| ``chars_per_token_estimate`` | int | 4 | 粗略 chars/token |

**microcompact**（再调轻量模型压摘要）与上表 ``summarize`` 路径合并实现，不再单独开关。

### max_turns 处理

- RunSpec.runtime.max_turns 限制**模型调用次数**（注意：turn = 一次模型推理调用，不是用户-助手对话轮数；ReAct 循环中每调一次模型即消耗 1 turn）
- 达到 max_turns 时：
  - 给模型发一条系统消息："已达到最大对话轮数，请给出当前最佳回答"
  - 最后一次调用模型
  - 返回结果，并提示用户"已达到对话上限，建议开新会话"

---

## Schema 校验

模型给出最终回答后，Agent Runner 按 RunSpec.output_schema 做校验。

### JSON Schema 加载路径

Agent Runner 按以下顺序查找 schema 文件：

```
1. Agent 级：agents/{agent_id}/schemas/{output_schema}.json
   └─→ 业务部门可在此放置自定义 schema，覆盖 Skill 默认行为

2. Skill 级：skills/{skill_id}/{skill_version}/schemas/{output_schema}.json
   └─→ Skill Creator 产出的标准 schema

3. 都不存在 → 跳过校验，返回 schema_valid: null
```

**加载方式**：

- 从 **Skill Registry** 拉取 Skill 级 schema（按 `skill_id + skill_version`）
- 从 **Agent App 注册中心** 拉取 Agent 级 schema（按 `agent_id`）
- 拉取后校验文件 hash 与 `RunSpec.skill_file_manifest['schemas/{output_schema}.json']` 是否匹配（防篡改）
- schema 文件常驻本地内存缓存（LRU，最多 50 个），避免重复拉取

### 校验流程

```
模型输出（JSON / Markdown / 文本）
  ↓
按上述路径加载 {output_schema}.json
  ↓
解析模型输出中的结构化内容
  ↓
校验：
  - 必填字段是否存在
  - 字段类型是否正确
  - 枚举值是否在范围内
  - Agent 级 schema 是否兼容 Skill 级 schema 的核心字段
  ↓
校验通过 → 返回给用户，标记 schema_valid: true
校验失败 → 给模型发"格式不符，请按 schema 重新输出" → 重新调用（最多重试 2 次）
```

#### Schema 向后兼容校验算法

当 Agent 级 schema 存在时，按以下规则判断兼容性：

| 规则 | 说明 | 违反动作 |
|------|------|---------|
| 超集原则 | Agent 级 schema 必须是 Skill 级 schema 的 **superset** | 拒绝 Agent 级 schema，回退到 Skill 级 |
| 核心字段不可删 | Skill 级 `required` 中的字段在 Agent 级中必须仍为 `required` | 拒绝 Agent 级 schema |
| 类型不可变 | Skill 级已声明字段的 `type` 在 Agent 级中不可变更 | 拒绝 Agent 级 schema |
| 允许新增 | Agent 级可新增字段、新增 `required`（仅限新增字段） | 允许 |
| 允许追加描述 | Agent 级可为已有字段追加 `description`、`examples` | 允许 |

**实现方式**：递归对比两个 JSON Schema 的 `properties` 和 `required` 节点。Agent 级缺失 Skill 级要求的字段 → 不兼容；Agent 级改字段类型 → 不兼容；其他情况 → 兼容。

**注意**：schema 校验失败不阻塞用户——第 3 次仍失败则返回原始文本，并标记 `schema_validation_failed: true`。

---

## 工具调用格式

模型输出中的工具调用必须按以下格式（对齐 OpenAI function calling）：

```json
{
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "kb.search",
        "arguments": "{\"query\": \"付款条款 违约金\", \"scope\": \"group_legal_policy\"}"
      }
    }
  ]
}
```

Runner 解析后：

1. 检查 `name` 是否在 RunSpec.allowed_tools 中
2. 用 Tool Registry 的 `input_schema` 校验参数
3. 调用 Tool Gateway
4. 将结果格式化为：

```json
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "content": "..."
}
```

---

## 模型输出解析器（Output Parser）

模型原始输出可能混有 Markdown、解释文本和结构化 JSON。Runner 的解析器负责**可靠提取** tool_calls 或最终回答。

### 解析流程

```
模型原始输出（字符串）
  ↓
1. 尝试标准 JSON 解析（整个输出为 JSON）
   ├─→ 成功 → 检查是否有 "tool_calls" 字段
   └─→ 失败 → 步骤 2
  ↓
2. Markdown 代码块提取
   ├─→ 查找 ```json ... ``` 或 ``` ... ``` 块
   ├─→ 提取块内内容再次 JSON 解析
   └─→ 失败 → 步骤 3
  ↓
3. 正则兜底提取
   ├─→ 搜索 "tool_calls" 关键字后的 JSON 对象
   ├─→ 使用平衡括号算法提取完整 JSON
   └─→ 失败 → 步骤 4
  ↓
4. 纯文本兜底
   └─→ 无 tool_calls → 视为最终回答文本
```

### 解析失败兜底策略

| 场景 | 处理 |
|------|------|
| JSON 格式合法但缺少 `tool_calls` | 视为最终回答，进入 schema 校验 |
| JSON 格式合法但 `tool_calls` 为空数组 | 视为最终回答 |
| `tool_calls` 存在但 `name` 不在 `allowed_tools` 中 | 返回 `"Tool {name} not in RunSpec allowed_tools"`，模型自行修正 |
| `arguments` 不是合法 JSON 字符串 | 返回 `"Invalid arguments format for {name}"` |
| 完全无法解析 | 视为最终回答文本，跳过 schema 校验（标记 `schema_valid: null`） |

### 伪代码实现

```python
def parse_model_output(raw: str, allowed_tools: list[str]) -> ModelOutput:
    # 1. 标准 JSON
    try:
        data = json.loads(raw)
        if "tool_calls" in data:
            return ToolCallOutput(tool_calls=data["tool_calls"])
        return FinalAnswerOutput(content=raw)
    except json.JSONDecodeError:
        pass

    # 2. Markdown 代码块
    code_block = extract_markdown_json(raw)
    if code_block:
        try:
            data = json.loads(code_block)
            if "tool_calls" in data:
                return ToolCallOutput(tool_calls=data["tool_calls"])
        except json.JSONDecodeError:
            pass

    # 3. 正则提取
    match = re.search(r'"tool_calls"\s*:\s*(\[.*?\])', raw, re.DOTALL)
    if match:
        try:
            tool_calls = json.loads(match.group(1))
            return ToolCallOutput(tool_calls=tool_calls)
        except json.JSONDecodeError:
            pass

    # 4. 兜底：纯文本
    return FinalAnswerOutput(content=raw)
```

**与 Checkpoint 的对齐**：解析器在每个 turn 完成后将完整消息（含 tool_calls 或最终回答）写入 checkpoint，确保恢复时消息历史完整。

---

## 错误处理

| 错误场景 | 处理 |
|---------|------|
| 模型调用超时 | fallback 到 fallback_model；再超时则返回"服务繁忙，请稍后重试" |
| 模型调用错误 | 记录错误码，返回友好提示 |
| 工具调用超时 | 返回"工具响应超时"给模型，让模型决定是否重试 |
| 工具调用权限拒绝 | Runner 层不应发生（Compiler 已算交集），如发生则报错终止 |
| schema 校验失败 | 最多重试 2 次，第 3 次返回原始文本 + 标记 |
| 上下文超 token 上限 | 触发 history snip，仍超则提示开新会话 |

---

## 与 Tool Gateway 的交互

```
Agent Runner ──→ Tool Gateway
  POST /execute
  Body: {
    "run_id": "run_20260506_001",
    "tool_id": "kb.search",
    "params": {...},
    "allowed_scopes": ["group_legal_policy"],
    "timeout": 10
  }

Tool Gateway ──→ Agent Runner
  Response: {
    "status": "success",
    "result": {...},
    "latency_ms": 150
  }
```

---

## Runner 状态机

```
          ┌─────────────┐
          │   created   │
          └──────┬──────┘
                 ↓ 收到用户输入
          ┌─────────────┐
          │  running    │
          └──────┬──────┘
       ┌────────┼────────┐
       ↓        ↓        ↓
┌──────────┐ ┌──────┐ ┌────────┐
│ completed│ │error │ │timeout │
└──────────┘ └──────┘ └────────┘
```

- **created**：RunSpec 已生成，等待第一条用户消息
- **running**：正在执行工具调用循环
- **completed**：给出最终回答
- **error**：发生不可恢复错误
- **timeout**：总耗时超过 RunSpec.runtime.timeout_seconds

---

## Checkpoint 机制

### 什么是 Checkpoint

**Checkpoint = 会话执行过程中的"存档点"**，每完成一轮模型调用 + 工具调用后自动保存当前状态。用于：

1. **错误恢复**：某轮工具调用失败后，从上一个 checkpoint 恢复，不丢失已完成的上下文
2. **审计复现**：事后按 checkpoint 序列完整重建会话执行过程
3. **长会话保护**：浏览器刷新后从最近 checkpoint 恢复，而不是从头开始

### Checkpoint 内容

```yaml
checkpoint:
  checkpoint_id: cp_001
  run_id: run_20260507_001
  runspec_schema_version: 1   # RunSpec schema 版本，用于恢复时兼容性校验
  turn_number: 2              # 第几轮完成后存的档
  timestamp: "2026-05-07T14:30:00Z"
  messages:                   # 截至当前的完整消息历史
    - { role: "system", content: "..." }
    - { role: "user", content: "请审查这份合同" }
    - { role: "assistant", tool_calls: [...] }
    - { role: "tool", content: "..." }
  token_count: 3500           # 当前累计 token
  tool_calls_so_far:          # 已完成的工具调用记录
    - { tool_id: "kb.search", status: "success", latency_ms: 150 }
```

### 存储策略

| 场景 | 存储位置 | TTL |
|------|---------|-----|
| 活跃会话的 checkpoint | Redis（Hash） | session 过期时间 |
| 已结束会话的 checkpoint | PostgreSQL（归档） | audit.retain_days |
| 浏览器端恢复用 | IndexedDB（widget 缓存最近 1 个） | 30 天 |

### Checkpoint 归档迁移机制

会话状态变为 `completed` / `error` / `timeout` 后，由异步 worker（Redis Streams 消费者）执行迁移：

1. 从 Redis 读取该 session 的全部 checkpoint
2. 批量写入 PostgreSQL `checkpoints` 表
3. 删除 Redis 中的 checkpoint key
4. 若迁移失败（如 DB 瞬时不可用），checkpoint 保留在 Redis 中，由定时任务重试

**崩溃恢复**：若服务器在迁移前崩溃，Redis 中的 checkpoint 会因 TTL 过期自动清理（最多保留 session 过期时间），不会留下脏数据。

### 恢复流程

```
用户刷新页面 / 网络断线重连
  ↓
widget 上报 session_id + 最近 checkpoint_id
  ↓
Runner 从 Redis 加载 checkpoint
  ↓
校验 checkpoint.run_id == session.run_id
  ↓
恢复消息历史到模型上下文
  ↓
继续执行（不是重新编译 RunSpec）
```

**关键约束**：checkpoint 恢复**不改变 RunSpec**，只恢复执行状态。

#### Checkpoint 过期检测逻辑

```python
# 伪代码
async def resume_session(session_id, checkpoint_id):
    session = await db.get_session(session_id)

    # 权威来源：数据库 sessions.expires_at
    if session.expires_at < now():
        return { "error": "SESSION_EXPIRED", "message": "会话已超时，请开新会话" }

    # 校验 checkpoint 归属
    checkpoint = await redis.get(f"runspec:{session.run_id}:checkpoint:{checkpoint_id}")
    if checkpoint.run_id != session.run_id:
        return { "error": "RUNSPEC_MISMATCH", "message": "checkpoint 与会话不匹配" }

    # 校验 RunSpec schema 版本兼容性（向后兼容窗口 N=2）
    if checkpoint.runspec_schema_version < session.runspec_schema_version - 2:
        return { "error": "RUNSPEC_VERSION_MISMATCH", "message": "checkpoint 的 RunSpec 版本过旧，无法恢复，请开新会话" }

    # 恢复消息历史
    messages = checkpoint.messages
    return { "session_id": session_id, "run_id": session.run_id, "messages": messages }
```

#### Checkpoint Schema 兼容性校验

恢复 checkpoint 时，必须校验其 `runspec_schema_version` 与当前系统支持的版本范围兼容：

| 条件 | 行为 |
|------|------|
| checkpoint 版本 ≥ 当前版本 | 允许恢复（向前兼容，通常是同一版本） |
| checkpoint 版本 = 当前版本 - 1 或 -2 | 允许恢复（向后兼容窗口 N=2） |
| checkpoint 版本 < 当前版本 - 2 | **拒绝恢复**，返回 `RUNSPEC_VERSION_MISMATCH`，强制开新会话 |

**为什么 N=2**：RunSpec schema 升级遵循向后兼容原则，但超过 2 个版本的跨度可能引入无法安全恢复的结构变更（如字段语义变化、必填项新增）。拒绝过旧版本的恢复可避免状态不一致风险。

- **过期权威来源**：以数据库 `sessions.expires_at` 字段为准
- Redis TTL 和浏览器 cookie max-age 与之同步，但**最终判定以数据库为准**
- 默认超时：30 分钟无活动（可通过系统配置调整）

---

## Session Lock / Pending Queue / Mid-turn Injection

### Session Lock

**同一 session 同时只能有一个请求在执行**。

```python
# 伪代码
async def handle_chat(session_id, user_message, run_spec):
    # 锁超时必须覆盖完整模型调用周期（含工具调用），防止锁提前释放导致并发冲突
    lock_ttl = max(run_spec.runtime.timeout_seconds + 30, 120)
    acquired = await redis.set(f"lock:session:{session_id}", "1", nx=True, ex=lock_ttl)
    if not acquired:
        # session 正在被处理，消息进 pending queue
        await pending_queue.push(session_id, user_message)
        return { status: "queued", position: queue_length }
    try:
        # 执行工具调用循环
        result = await runner.execute(session_id, user_message)
        return result
    finally:
        await redis.delete(f"lock:session:{session_id}")
        # 检查 pending queue，如有消息继续处理
        await process_pending(session_id)
```

**锁超时策略**：
- 锁 TTL = `RunSpec.runtime.timeout_seconds + 30`（缓冲时间），最小不低于 120 秒
- 必须大于单次请求的总超时上限（含模型调用 90s、工具调用、doc.extract 大文件 60s），防止锁在请求完成前提前释放导致同一 session 并发执行
- 请求正常结束时立即主动释放锁（finally 块），TTL 只是死锁保护

### Pending Queue

用户连续发送多条消息时的处理策略：

| 策略 | 行为 | 适用场景 |
|------|------|---------|
| **默认：排队** | 新消息进 pending queue，当前轮完成后按 FIFO 处理 | 正常对话 |
| **合并** | 若 queue 中已有未处理消息，新消息与旧消息合并为一条 | 用户连续输入、纠错 |
| **丢弃** | 当前轮进行中时的新消息直接丢弃，提示"请稍等" | 极少使用 |

**队列长度上限**：5 条，超过则提示"发送过快，请稍后再试"。

### Mid-turn Injection

**问题**：模型正在思考或等待工具返回时，用户发了新消息。怎么处理？

**方案**：

```
状态：Runner 正在第 2 轮，已调模型，模型返回 tool_calls，Tool Gateway 执行中...
  ↓
用户发送新消息
  ↓
新消息进入 pending queue（不中断当前工具调用）
  ↓
当前工具调用完成，结果回传给模型
  ↓
模型继续完成当前轮（给出回答或下一轮 tool_calls）
  ↓
当前轮完成后，检查 pending queue
  ↓
如有新消息 → 作为下一轮用户输入继续
```

**为什么不中断**：工具调用可能是写操作（如提交审批），中断会导致状态不一致。必须等当前原子操作完成。

**例外**：若工具调用已超时（> timeout_seconds），则终止当前轮，从 pending queue 取新消息作为下一轮输入。
