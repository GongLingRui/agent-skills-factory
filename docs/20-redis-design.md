# 20. Redis Key 设计与缓存策略

> 版本：v0.6 · 2026-05-06

---

## Key 命名规范

统一采用 `领域:子领域:标识[:字段]` 的冒号分隔格式，便于按前缀扫描和管理。

### 1. Agent 相关

| Key 模式 | 类型 | TTL | 说明 |
|----------|------|-----|------|
| `agent:{agent_id}` | String (JSON) | 5min | agent.yaml 完整内容 |
| `agent:{agent_id}:version` | String | 5min | 当前生效版本号 |
| `agent:{agent_id}:versions` | Hash | 10min | 最近 10 个版本 {version -> json} |
| `agent:list:{department}` | Set | 5min | 某部门可见的 Agent ID 集合 |

### 2. Skill 相关

| Key 模式 | 类型 | TTL | 说明 |
|----------|------|-----|------|
| `skill:{skill_id}:{version}` | String (JSON) | 10min | Skill Package 元数据 |
| `skill:{skill_id}:latest` | String | 10min | 最新兼容版本号 |
| `skill:agents:{skill_id}` | Set | 10min | 挂载该 Skill 的所有 Agent ID |

### 3. Session / RunSpec 相关

| Key 模式 | 类型 | TTL | 说明 |
|----------|------|-----|------|
| `session:{session_id}` | Hash | 30min | 会话状态、run_id、user_id、turn_count |
| `runspec:{run_id}` | String (JSON) | 30min | RunSpec 完整内容 |
| `runspec:{run_id}:checkpoint:{cp_id}` | String (JSON) | 30min | Checkpoint 数据 |
| `lock:session:{session_id}` | String | 120s | Session Lock（SETNX），TTL = max(RunSpec.timeout + 30, 120)，防止锁在请求完成前提前释放 |
| `pending:{session_id}` | List | 30min | 待处理用户消息队列 |

### 4. 用户 / 权限相关

| Key 模式 | 类型 | TTL | 说明 |
|----------|------|-----|------|
| `user:{user_id}:perms` | Set | 5min | 用户权限码集合 |
| `user:{user_id}:domains` | Set | 5min | 用户可访问数据域 |
| `dept:{department}:perms` | Set | 5min | 部门默认权限 |
| `session:cookie:{session_cookie}` | Hash | 30min | session cookie 映射到 session_id |

### 5. 限流计数器

| Key 模式 | 类型 | TTL | 说明 |
|----------|------|-----|------|
| `ratelimit:user:{user_id}:{tool_id}` | String | 1min | 用户调用某工具的计数（滑动窗口） |
| `ratelimit:agent:{agent_id}:{tool_id}` | String | 1min | Agent 级别限流计数 |
| `ratelimit:global:{tool_id}` | String | 1min | 全局限流计数 |
| `ratelimit:dept:{department}:{tool_id}` | String | 1min | 部门级别限流计数 |

### 6. 模型网关相关

| Key 模式 | 类型 | TTL | 说明 |
|----------|------|-----|------|
| `model:{model_id}:health` | String | 10s | 模型健康状态 (healthy / degraded / down) |
| `model:{model_id}:tpm` | String | 1min | 当前分钟已用 token 数 |
| `model:queue:{class}` | Sorted Set | - | 各优先级队列（privileged / interactive / document / batch），score = priority * 1e12 + timestamp |
| `cache:prompt:{hash}` | String | 60s | 相同 prompt 的结果缓存 |

### 7. 降级状态

| Key 模式 | 类型 | TTL | 说明 |
|----------|------|-----|------|
| `degradation:level` | String | - | 当前系统降级级别（0-6），无 TTL，手动或自动触发 |
| `degradation:since` | String | - | 降级开始时间戳 |
| `degradation:reason` | String | - | 降级原因 |

### 9. JWT 黑名单

| Key 模式 | 类型 | TTL | 说明 |
|----------|------|-----|------|
| `jwt:jti:{jti}` | String | 300s | short-lived JWT 一次性使用标记，已消费即写入，防重放攻击 |

### 10. Pub/Sub Channel

| Channel | 说明 |
|---------|------|
| `skill:updated` | Skill 升级通知 |
| `agent:updated` | Agent 配置更新通知 |
| `policy:updated` | platform_policy / org_policy 变更通知 |
| `degradation:changed` | 降级级别变更通知 |

---

## 模型队列优先级实现

```python
# 伪代码：入队
async def enqueue(model_request):
    # score 高 bit 存 priority，低 bit 存时间戳，保证同优先级 FIFO
    score = request.priority * 1_000_000_000_000 + request.timestamp_ms
    await redis.zadd(f"model:queue:{request.concurrency_class}", {request.id: score})

# 伪代码：出队
async def dequeue(concurrency_class):
    # 弹出 score 最小的请求（优先级高 + 先入队）
    items = await redis.zpopmin(f"model:queue:{concurrency_class}", count=1)
    return items[0] if items else None
```

**为什么用 Sorted Set 而不是 List**：List 是严格 FIFO，无法实现 `queue_priority`（1-10）的优先级出队。Sorted Set 的 score 同时编码优先级和时间戳，既保证高优先级优先，又保证同优先级 FIFO。

---

## 限流计数器实现

### 滑动窗口（推荐）

```python
# 伪代码：检查用户是否超过 60/min 的配额
async def check_rate_limit(user_id, tool_id, max_per_minute=60):
    key = f"ratelimit:user:{user_id}:{tool_id}"
    now = time.time()
    window_start = now - 60

    # 使用 Redis Sorted Set：score = 时间戳，member = 唯一请求 ID
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)   # 清理过期窗口
    pipe.zcard(key)                                # 当前窗口内请求数
    pipe.zadd(key, {str(uuid4()): now})           # 记录本次请求
    pipe.expire(key, 120)                          # 兜底过期
    _, current_count, _, _ = await pipe.execute()

    if current_count >= max_per_minute:
        raise RateLimitExceeded()
```

---

## 缓存一致性策略

### 写穿透（Write-Through）

Agent / Skill / Policy 的更新：

1. 先写数据库（主库）
2. 再写 Redis
3. 最后发布 Pub/Sub 通知其他实例清除本地缓存

### 读穿透（Read-Through）

```python
async def get_agent(agent_id):
    # 1. 查本地内存缓存（Caffeine / LRU Cache）
    local = local_cache.get(f"agent:{agent_id}")
    if local:
        return local

    # 2. 查 Redis
    redis_val = await redis.get(f"agent:{agent_id}")
    if redis_val:
        agent = json.loads(redis_val)
        local_cache.set(f"agent:{agent_id}", agent)
        return agent

    # 3. 回源数据库
    agent = await db.query("SELECT * FROM agent_apps WHERE id = ?", agent_id)
    await redis.setex(f"agent:{agent_id}", 300, json.dumps(agent))
    local_cache.set(f"agent:{agent_id}", agent)
    return agent
```

### 缓存雪崩防护

热点 Agent（如制度问答）缓存失效时：

```python
async def get_agent_with_lock(agent_id):
    lock_key = f"agent:{agent_id}:refresh_lock"
    locked = await redis.set(lock_key, "1", nx=True, ex=10)
    if not locked:
        # 其他实例正在回源，等待 100ms 后重试读 Redis
        await asyncio.sleep(0.1)
        return await get_agent(agent_id)
    try:
        return await get_agent(agent_id)
    finally:
        await redis.delete(lock_key)
```

---

## Redis 核心数据结构与读写命令

| Key 模式 | 类型 | 核心命令 | 说明 |
|----------|------|---------|------|
| `agent:{agent_id}` | String (JSON) | `GET / SETEX` | agent.yaml 完整内容 |
| `agent:{agent_id}:version` | String | `GET / SETEX` | 当前生效版本号 |
| `agent:{agent_id}:versions` | Hash | `HGET / HGETALL / HSET` | 最近 10 个版本 |
| `agent:list:{department}` | Set | `SMEMBERS / SADD` | 某部门可见 Agent ID 集合 |
| `skill:{skill_id}:{version}` | String (JSON) | `GET / SETEX` | Skill Package 元数据 |
| `session:{session_id}` | Hash | `HGETALL / HMSET` | 会话状态、run_id、user_id |
| `runspec:{run_id}` | String (JSON) | `GET / SETEX` | RunSpec 完整内容 |
| `runspec:{run_id}:checkpoint:{cp_id}` | Hash | `HGETALL / HMSET` | Checkpoint 数据 |
| `lock:session:{session_id}` | String | `SET NX EX / DEL` | Session Lock（SETNX） |
| `pending:{session_id}` | List | `RPUSH / LPOP / LLEN` | 待处理用户消息队列 |
| `user:{user_id}:perms` | Set | `SMEMBERS / SISMEMBER` | 用户权限码集合 |
| `user:{user_id}:domains` | Set | `SMEMBERS` | 用户可访问数据域 |
| `ratelimit:user:{uid}:{tool}` | Sorted Set | `ZREMRANGEBYSCORE / ZCARD / ZADD` | 滑动窗口限流 |
| `model:{model_id}:health` | String | `GET / SETEX` | 模型健康状态 |
| `model:queue:{class}` | Sorted Set | `ZADD / ZPOPMIN` | 优先级队列 |
| `degradation:level` | String | `GET / SET` | 当前降级级别 |
| `jwt:jti:{jti}` | String | `SET EX` | short-lived JWT 一次性标记 |

### Checkpoint 存储对齐

与 [08-agent-runner.md](08-agent-runner.md) §Checkpoint 机制对齐：

```
# 活跃会话的 checkpoint 存 Redis Hash
HSET "runspec:{run_id}:checkpoint:{cp_id}" \
  checkpoint_id "cp_001" \
  run_id "run_20260507_001" \
  turn_number "2" \
  timestamp "2026-05-07T14:30:00Z" \
  messages "[...JSON...]" \
  token_count "3500" \
  tool_calls_so_far "[...JSON...]"

# TTL = session 过期时间（30 分钟）
EXPIRE "runspec:{run_id}:checkpoint:{cp_id}" 1800
```

---

## 容量规划

| 数据类型 | 单条大小 | 峰值数量 | 总内存 |
|----------|---------|---------|--------|
| agent.yaml | ~5KB | 1000 个 | ~5MB |
| session | ~2KB | 10000 个 | ~20MB |
| RunSpec | ~10KB | 10000 个 | ~100MB |
| 限流计数器 | ~100B | 100000 个 | ~10MB |
| prompt 缓存 | ~20KB | 1000 个 | ~20MB |
| **合计** | | | **~155MB** |

Redis 实例配置 8GB 内存，绰绰有余。主要瓶颈是连接数而非内存。
