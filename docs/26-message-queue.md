# 26. 消息队列与异步任务设计

> 版本：v0.6 · 2026-05-06

---

## 一句话职责

**承接所有非实时、可异步执行的后台任务**，保证可靠投递、失败重试、最终一致。

**类比**：医院挂号后的化验科——抽血是实时的，但验血报告异步出，系统保证你的报告不会丢、不会乱序、出错会重做一次。

---

## 哪些任务走异步队列

| 任务类型 | 实时性要求 | 入队时机 | 消费方 |
|---------|-----------|---------|--------|
| **审计日志写入** | 低 | 每轮对话/工具调用后 | Audit Worker |
| **Checkpoint 保存** | 中 | 每轮完成后 | Checkpoint Worker |
| **文件解析（大文件）** | 中 | 用户上传后 | Doc Worker |
| **脚本执行** | 中 | 模型调用脚本工具时 | Script Worker |
| **Schema 校验失败重试** | 中 | 校验失败后 | Runner 内部调度 |
| **Token 预算扣减** | 低 | 模型调用完成后 | Quota Worker |
| **数据归档** | 低 | 每日凌晨 | Archive Worker |
| **MAU 统计汇总** | 低 | 每日凌晨 | Stats Worker |
| **会话过期清理** | 低 | 会话超时后 | Cleanup Worker |
| **邮件/企微通知** | 低 | 异常事件触发时 | Notify Worker |

**不走队列（同步执行）**：
- 模型调用（必须实时返回 SSE）
- 小型文件解析（<10MB，同步返回）
- 用户登录/身份校验

---

## 队列选型

**使用 Redis Streams** 作为默认消息队列：

| 方案 | 评估 | 结论 |
|------|------|------|
| Redis Streams | 已有 Redis 基础设施；支持消费者组、ACK、自动重试 | **选用** |
| RabbitMQ | 功能完善，但需额外部署 | 未来流量增长后考虑 |
| Kafka | 高吞吐，但运维重 | P3 阶段评估 |
| 数据库轮询 | 简单，但延迟高、资源浪费 | 不推荐 |

**Redis Streams 配置**：

```yaml
redis_streams:
  stream_prefix: "mq:"
  maxlen:                          # 按 stream 类型配置 maxlen，防无限增长
    audit: 200000                 # 审计高吞吐，保留最近 20 万条
    checkpoint: 50000             # checkpoint 中等吞吐
    file_extract: 20000           # 文件解析队列
    script: 20000                 # 脚本执行队列
    quota: 100000                 # 预算扣减，可积压
    archive: 1000                 # 归档任务低频
    stats: 1000                   # 统计任务低频
    notify: 50000                 # 通知队列
  consumer_group_prefix: "cg:"
  ack_timeout_seconds: 30         # 消费者必须在 30 秒内 ACK
  max_delivery_attempts: 3        # 最大投递次数
  dead_letter_stream: "mq:dlq"    # 死信队列
```

---

## 任务队列架构

```
┌─────────────────┐      ┌─────────────────────────────┐      ┌─────────────────┐
│   生产者        │─────>│      Redis Streams          │─────>│   消费者组       │
│  (API/Runner)   │      │  ┌─────────────────────┐    │      │  (Worker Pool)  │
└─────────────────┘      │  │ mq:audit            │    │      └─────────────────┘
                         │  │ mq:checkpoint       │    │             │
                         │  │ mq:file_extract     │    │             ↓
                         │  │ mq:script           │    │      ┌──────────────┐
                         │  │ mq:quota            │    │      │  DLQ 处理     │
                         │  │ mq:archive          │    │      │ (人工+告警)   │
                         │  │ mq:notify           │    │      └──────────────┘
                         │  └─────────────────────┘    │
                         └─────────────────────────────┘
```

---

## 消费者组设计

每条 stream 对应一个消费者组，支持多 Worker 并发消费：

| Stream | Consumer Group | Worker 数 | 说明 |
|--------|---------------|----------|------|
| `mq:audit` | `cg:audit` | 3 | 审计日志批量写入 PostgreSQL |
| `mq:checkpoint` | `cg:checkpoint` | 2 | checkpoint 保存到 Redis + 归档 |
| `mq:file_extract` | `cg:file_extract` | 5 | 大文件解析任务 |
| `mq:script` | `cg:script` | 5 | 受控脚本执行 |
| `mq:quota` | `cg:quota` | 2 | Token 预算异步扣减 |
| `mq:archive` | `cg:archive` | 1 | 数据归档（每日一次） |
| `mq:stats` | `cg:stats` | 1 | 每日统计汇总 |
| `mq:notify` | `cg:notify` | 2 | 通知发送 |

---

## 任务消息格式

```json
{
  "task_id": "task_20260507_001",
  "task_type": "audit_log",
  "priority": 5,
  "created_at": "2026-05-07T14:30:00Z",
  "payload": {
    "run_id": "run_20260507_001",
    "session_id": "sess_abc123",
    "level": "minimal",
    "tool_calls": [...],
    "token_count": 3500
  },
  "retry_count": 0,
  "max_retries": 3,
  "deadline": "2026-05-07T14:35:00Z"
}
```

**优先级**：1-10，数字越大优先级越高。`privileged` 类会话的审计任务优先级为 9，`batch` 类为 3。

---

## 可靠性保证

### 至少一次投递（At-Least-Once）

1. 生产者 XADD 到 stream
2. 消费者 XREADGROUP 读取
3. 消费者处理完成后 XACK
4. 若消费者崩溃未 ACK，Redis 保留 pending 列表，其他消费者可 XPENDING + XCLAIM  reclaim

### 失败重试

```python
# 伪代码
async def process_message(msg):
    try:
        result = await handle(msg.payload)
        await redis.xack(stream, group, msg.id)
    except RetryableError:
        if msg.retry_count < msg.max_retries:
            await redis.xadd(stream, {**msg, retry_count: msg.retry_count + 1})
            await redis.xack(stream, group, msg.id)
        else:
            await redis.xadd(dlq_stream, msg)
            await redis.xack(stream, group, msg.id)
    except NonRetryableError:
        await redis.xadd(dlq_stream, msg)
        await redis.xack(stream, group, msg.id)
```

### 死信队列（DLQ）

- 超过最大重试次数的任务进入 `mq:dlq`
- DLQ 任务保留 7 天，供人工排查
- 告警规则：DLQ 长度 > 10 时触发企微/邮件告警

---

## 延迟任务

部分任务需要延迟执行：

| 场景 | 延迟时间 | 实现方式 |
|------|---------|---------|
| 会话过期清理 | session 超时后 | Redis Keyspace Notification + 回调 |
| Token 预算重置 | 每月 1 日 00:00 | cron 任务（见 [21-cron-jobs.md](21-cron-jobs.md)） |
| 审计日志归档 | 90 天后 | 定时任务扫描 `retention_until` |

**延迟队列实现**：Redis Sorted Set（`zset`），score 为执行时间戳。为避免分布式多实例重复消费，采用 **单 Leader 抢锁 + 原子 ZPOPMIN** 双保险。

```python
# 伪代码：添加延迟任务
async def schedule_delayed_task(task, delay_seconds):
    execute_at = time.time() + delay_seconds
    await redis.zadd("mq:delayed", {task_id: execute_at})
    await redis.set(f"mq:delayed:payload:{task_id}", task)

# 定时轮询（每 5 秒，仅由当前 Leader 实例执行）
async def poll_delayed_tasks():
    # 抢 Leader 锁（10 秒 TTL，需心跳续期）
    is_leader = await redis.set("mq:delayed:leader", node_id, nx=True, ex=10)
    if not is_leader:
        return

    while True:
        # 原子弹出已到期的任务（避免多实例竞争）
        # Redis 6.2+ 使用 ZPOPMIN；低于 6.2 用 Lua 脚本模拟
        due = await redis.zpopmin("mq:delayed", count=10)
        if not due:
            break
        for task_id, score in due:
            task = await redis.get(f"mq:delayed:payload:{task_id}")
            if task:
                await redis.xadd(f"mq:{task['task_type']}", task)
                await redis.delete(f"mq:delayed:payload:{task_id}")

# 降级方案（Redis < 6.2）：Lua 脚本保证 ZRANGEBYRANK + ZREM 原子性
DELAYED_POP_LUA = """
local items = redis.call('zrangebyscore', KEYS[1], 0, ARGV[1], 'limit', 0, ARGV[2])
if #items > 0 then
    redis.call('zremrangebyrank', KEYS[1], 0, #items - 1)
end
return items
"""
```

**关键约束**：
- Leader 锁每 5 秒续期一次，实例宕机后 10 秒内自动选举新 Leader
- `zpopmin` 或 Lua 脚本保证"查询 + 删除"原子性，杜绝重复消费
- 任务执行失败（xadd 异常）时，payload 暂不删除，由死信检查任务后续处理

---

## 背压与限流

### 生产者限流

当 stream 长度超过阈值时，生产者暂停入队或降级：

| Stream | maxlen 阈值 | 超限动作 |
|--------|------------|---------|
| `mq:audit` | 50000 | 阻塞入队，等待消费 |
| `mq:checkpoint` | 10000 | 丢弃非活跃会话的 checkpoint（保留最近 1 个） |
| `mq:file_extract` | 5000 | 返回"文件解析队列已满，请稍后重试" |
| `mq:script` | 3000 | 返回"脚本执行队列已满" |

### 消费者扩容

- CPU > 70% 或 pending 消息 > 1000 时，HPA 自动扩容 Worker Pod
- 最小副本数：1；最大副本数：按任务类型配置（脚本 Worker 最多 20，审计 Worker 最多 10）

---

## 监控指标

| 指标 | 采集方式 | 告警阈值 |
|------|---------|---------|
| 各 stream 长度 | Redis XLEN | > maxlen * 80% |
| pending 消息数 | Redis XPENDING | > 1000 持续 5 分钟 |
| 消费延迟（消息入队到 ACK 时间） | 任务消息内 timestamp | P99 > 30 秒 |
| DLQ 长度 | Redis XLEN mq:dlq | > 10 |
| Worker 处理失败率 | 消费者日志 | > 5% |
