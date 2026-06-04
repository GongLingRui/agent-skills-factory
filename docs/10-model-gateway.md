# 10. 模型网关与队列

> 版本：v0.6 · 2026-05-06

---

## 一句话职责

模型路由、限流、fallback、token 预算。

**类比**：调度中心——谁的需求送哪个工厂、工厂满了怎么办、工厂坏了怎么换、总共用了多少原料。

---

## 核心功能

| 功能 | 说明 |
|------|------|
| 路由 | 按模型名称路由到对应后端（国产模型 / OpenAI 兼容网关） |
| 队列 | LLM 请求进队列，按优先级出队 |
| fallback | 首选模型不可用时自动降级 |
| token 预算 | 按用户 / 部门 / Agent 限制 token 消耗 |
| 批处理 | Embedding 请求合并批处理 |
| 缓存 | 相同 prompt 的结果缓存（短时间） |

---

## MiniMax（OpenAI 兼容）

- **Base URL**（`ModelClient` 会请求 `endpoint + /chat/completions`）须与 **密钥所属站点** 一致：
  - **国内**（[platform.minimaxi.com](https://platform.minimaxi.com/docs/api-reference/text-chat-openai)）：`https://api.minimaxi.com/v1`
  - **国际**（[platform.minimax.io](https://platform.minimax.io/docs/api-reference/text-chat-openai)）：`https://api.minimax.io/v1`
- 旧域名 **`api.minimax.chat`** 已废弃/易 **502**，请勿再使用。
- 国内密钥配国际域名（或反之）会 **401 invalid api key**；请改 `models.yaml` 中对应模型的 `endpoint`。
- 本地自检：`cd backend && uv run python scripts/test_minimax_openai_chat.py`（可选参数传入另一 Base URL）。

## 多模型与 OpenAI 兼容体（对齐 Claude Code 式「路由 + 别名」）

- **`models.yaml` 顶层 `model_aliases`**：把 Widget/门户里的短名映射到 `models` 下的逻辑键（例如 `default` → `MiniMax-M2.7`），`ModelGateway.resolve_model` 在解析前会先展开别名。
- **每条 `models.<id>` 可选 `api_model`**：HTTP `POST .../chat/completions` 的 JSON 里 `model` 字段使用该值；未配置时仍用逻辑键 `id`。便于 MiniMax / 自建 vLLM 等「逻辑名与供应商 model id 不一致」的场景。
- **`GET /api/v1/agents/catalog/models`**：返回已配置的模型列表、别名表、平台默认模型，供前端做模型切换器（需登录态）。
- **会话级覆盖**：`POST /agents/{id}/init` 的 JSON 可带 `"model": "<逻辑键或别名>"`，在 RunSpec 编译时写入 `runtime.model`（须已在 `models.yaml` 注册）；非法值返回 **`INVALID_MODEL`**。`POST .../new-session` 支持查询参数 `?model=`（便于无 body 的客户端）。

---

## 路由规则

```yaml
# 模型配置（平台管理员维护）
models:
  qwen3-32b:
    provider: local
    endpoint: http://qwen3-32b.internal:8000/v1
    max_tokens: 32768
    rpm: 100
    tpm: 100000

  qwen3-14b:
    provider: local
    endpoint: http://qwen3-14b.internal:8000/v1
    max_tokens: 32768
    rpm: 200
    tpm: 200000

  qwen3-8b:
    provider: local
    endpoint: http://qwen3-8b.internal:8000/v1
    max_tokens: 32768
    rpm: 500
    tpm: 500000
```

### 路由流程

```
Agent Runner 请求模型
  ↓
1. 解析 RunSpec.runtime.model → qwen3-32b
  ↓
2. 检查该模型是否可用
   ├─→ 可用 → 发请求
   └─→ 不可用 → fallback
  ↓
3. fallback 链：
   qwen3-32b → qwen3-14b → qwen3-8b → 报错
  ↓
4. 请求进入队列（按 concurrency.queue_priority 排序）
  ↓
5. 出队 → 发 HTTP 请求 → 流式返回（SSE）
```

---

## 队列设计

### 队列分级

```
┌─────────────────────────┐
│    privileged 队列      │  ← 最高优先级，插在最前面
├─────────────────────────┤
│    interactive 队列     │  ← 普通问答
├─────────────────────────┤
│    document 队列        │  ← 文档处理
├─────────────────────────┤
│    batch 队列           │  ← 批量任务，最后处理
└─────────────────────────┘
```

### 队列参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_queue_size | 1000 | 单队列最大长度 |
| queue_timeout | 300s | 队列中最大等待时间 |
| request_timeout | 60s | 模型响应最大等待时间 |
| max_retry | 2 | 失败后重试次数 |

---

## Token 预算

### 预算层级

```
平台总预算（平台管理员设置）
  ├─→ 部门预算（按部门分配）
  │     ├─→ Agent 预算（按 Agent 分配）
  │     │     └─→ 用户预算（可选，按用户限制）
```

### 预算超限处理

| 层级 | 超限动作 |
|------|---------|
| 用户预算 | 提示"个人额度已用完，请联系管理员" |
| Agent 预算 | 该 Agent 拒绝新请求，不影响其他 Agent |
| 部门预算 | 该部门所有 Agent 降级到 low_cost 模型 |
| 平台总预算 | 全平台 batch 任务暂停，interactive 降级 |

### 预算重置与透支策略

| 策略项 | 规则 |
|--------|------|
| **重置周期** | 每月 1 日 00:00:00 自动重置 `used_tokens = 0`，创建新周期记录 |
| **重置触发** | 由 cron 任务执行（详见 [21-cron-jobs.md](21-cron-jobs.md)），同时清理上月过期缓存 |
| **硬 stop / soft warning** | 用户/Agent 级：hard stop（拒绝新请求）；部门/平台级：soft warning（降级到 low_cost，不拒绝） |
| **额度查询 API** | `GET /api/v1/usage/quota`（用户侧）返回当前 scope 剩余额度；`GET /admin/token-quotas`（管理侧）返回全量 |
| **透支** | **不允许透支**。到达预算上限即触发对应超限动作，无缓冲额度 |
| **临时调额** | 部门管理员可通过 `/admin/token-quotas` 接口即时调高当月预算（`effective_next_period=false`），无需等下月 |

---

## Fallback 策略

### 触发条件

| 条件 | 动作 |
|------|------|
| 模型返回 429 / 503 | 立即 fallback |
| 模型响应 P99 > 30s | 下一请求 fallback |
| 模型错误率 > 5%（1 分钟） | 该模型标记为 degraded，持续 fallback |
| 模型完全不可达 | 永久 fallback 直到恢复 |

### Fallback 链

```
RunSpec.runtime.model: qwen3-32b
  ↓ 不可用
RunSpec.runtime.fallback_model: qwen3-14b
  ↓ 不可用
系统默认兜底: qwen3-8b
  ↓ 不可用
返回错误: "所有模型不可用，请稍后重试"
```

---

## Embedding 批处理

Embedding 请求（用于知识检索）走独立队列，支持批处理：

```
收到 Embedding 请求
  ↓
缓冲 100ms，收集同批次请求
  ↓
合并成一个 batch 请求发给模型
  ↓
结果拆分返回给各调用方
```

---

## 队列调度策略

### 调度算法

模型网关采用 **多级优先级队列（Multi-Level Priority Queue）**，每个并发类（interactive / document / batch / privileged）对应一个独立队列：

```python
# 入队逻辑
async def enqueue(request):
    queue_name = f"model:queue:{request.concurrency_class}"
    # score 高 bit 存优先级（1-10），低 bit 存时间戳，保证同优先级 FIFO
    score = request.queue_priority * 1_000_000_000_000 + request.timestamp_ms
    await redis.zadd(queue_name, {request.id: score})

# 出队逻辑（每个并发类独立出队）
async def dequeue(concurrency_class):
    queue_name = f"model:queue:{concurrency_class}"
    items = await redis.zpopmin(queue_name, count=1)
    return items[0] if items else None
```

### 调度优先级规则

| 请求来源 | concurrency_class | queue_priority | 插队策略 |
|----------|-------------------|----------------|----------|
| 特权 Agent（degradation_exempt=true） | privileged | 10 | 直接插入 privileged 队首 |
| 普通对话（用户实时交互） | interactive | 5（默认） | 按 score 正常排序 |
| 文档处理（上传后解析） | document | 3 | 按 score 正常排序 |
| 批量任务 | batch | 1 | 按 score 正常排序，CPU 空闲时批量消费 |

### 队列容量与反压

| 并发类 | 最大队列长度 | 超限行为 |
|--------|-------------|----------|
| privileged | 100 | 拒绝新请求，返回 `MODEL_UNAVAILABLE` |
| interactive | 1000 | 返回 429，带 `Retry-After: 5` |
| document | 500 | 返回 429，带 `Retry-After: 30` |
| batch | 2000 | 静默丢弃最老的 batch 请求（可接受） |

### `degradation_exempt` 的插队实现

```python
# 当 Agent 标记了 degradation_exempt=true 时：
# 1. 请求不进入原并发类队列，直接进入 privileged 队列
# 2. 如果 privileged 队列已满，优先驱逐 interactive 队列中优先级最低的请求
#    （interactive 请求被降级为 "等待"，给用户提示"服务繁忙，请稍候"）
```

**公平性保证**：同一用户的高优先级请求不会完全挤占低优先级请求。出队器每处理 5 个 privileged/interactive 请求后，强制处理 1 个 document 和 1 个 batch 请求（如果队列非空），防止饥饿。

### 优先级老化（Priority Aging）

为防止高优先级请求持续涌入导致低优先级请求饿死，引入**优先级老化**机制：

| 等待时间 | 老化动作 | 说明 |
|---------|---------|------|
| > 30s | `priority += 1` | 优先级临时提升 1 级 |
| > 60s | `priority += 1` | 再次提升，最多与最高优先级持平 |
| > 120s | 强制出队 | 无论优先级直接处理（防止无限等待） |

**老化实现**：

```python
async def dequeue_with_aging(concurrency_class):
    queue_name = f"model:queue:{concurrency_class}"
    # 1. 先检查是否有等待超过 120s 的请求
    old_items = await redis.zrangebyscore(queue_name, 0, now_ms - 120_000)
    if old_items:
        await redis.zrem(queue_name, old_items[0])
        return old_items[0]

    # 2. 正常按 score 出队（score 已包含老化后的优先级）
    items = await redis.zpopmin(queue_name, count=1)
    return items[0] if items else None
```

**老化对 score 的影响**：入队时 `score = priority * 1e12 + timestamp`，老化不改变已入队 score，而是在出队前按当前等待时间重新计算 effective_priority，与队首 score 比对后决定是否插队。

---

## 缓存策略

| 类型 | TTL | 说明 |
|------|-----|------|
| 相同 prompt 缓存 | 60s | 完全相同的 prompt 在 60s 内复用结果 |
| 模型可用性缓存 | 10s | 模型健康状态 10s 内不重复探测 |
| 路由配置缓存 | 5min | 模型配置 5 分钟内不重复加载 |

---

## 接口

```
POST /v1/chat/completions
  Headers: Authorization: Bearer <internal-token>
  Body: {
    "model": "qwen3-32b",
    "messages": [...],
    "max_tokens": 8000,
    "stream": true
  }
  Response: SSE stream

POST /v1/embeddings
  Body: {
    "model": "bge-m3",
    "input": ["text1", "text2", ...]
  }
```

**注意**：模型网关对外暴露 OpenAI 兼容接口，内部路由到不同国产模型后端。
