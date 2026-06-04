# 21. 定时任务清单

> 版本：v0.6 · 2026-05-06

---

## 任务总览

| 任务名 | 频率 | 执行时段 | 负责模块 | 优先级 |
|--------|------|---------|---------|--------|
| MAU 体检与自动归档 | 每日 02:00 | 夜间低峰 | Agent App 注册中心 | 高 |
| 审计日志清理 | 每日 03:00 | 夜间低峰 | 审计模块 | 高 |
| Agent 使用统计汇总 | 每日 04:00 | 夜间低峰 | 观测性模块 | 中 |
| 备份完整性验证 | 每周日 01:00 | 周末 | 运维 | 高 |
| Salt 轮换 | 每季度首月 1 日 00:00 | 凌晨 | 安全模块 | 高 |
| 缓存预热（热点 Agent） | 每 5 分钟 | 持续 | Core 服务 | 低 |
| 会话过期清理 | 每 10 分钟 | 持续 | Core 服务 | 中 |
| 模型健康探测 | 每 10 秒 | 持续 | 模型网关 | 高 |
| 降级自动恢复检查 | 每 1 分钟 | 持续 | 降级控制模块 | 高 |
| 反馈数据汇总 | 每日 05:00 | 夜间低峰 | 观测性模块 | 低 |
| 过期文件清理 | 每日 02:30 | 夜间低峰 | 文档解析 Worker | 中 |
| Token 预算重置 | 每月 1 日 00:00 | 凌晨 | 模型网关 | 高 |

---

## 详细任务说明

### 1. MAU 体检与自动归档

**执行模块**：Agent App 注册中心

**频率**：每日 02:00（夜间低峰）

**流程**：

```python
def mau_health_check():
    for agent in agent_registry.list_active():
        # 计算过去 30 天 MAU
        mau = usage_log.count_unique_users(agent.id, days=30)

        if mau < agent.mau_threshold:
            # 体检不达标
            agent.lifecycle_state = "cold"
            agent.cold_since = now()
            notify_department(agent.owner, f"Agent {agent.name} MAU 不达标，已转入 cold registry")

        # 已在 cold 状态超过 90 天 → archived
        if agent.lifecycle_state == "cold" and agent.cold_since > 90_days_ago:
            agent.lifecycle_state = "archived"
            notify_platform_admin(f"Agent {agent.name} 已自动归档")
```

**配置项**：

- `mau_threshold`：默认 5（30 天内少于 5 个不同用户使用则进入 cold）
- 业务部门可在 agent.yaml 中自定义 `enterprise.mau_threshold`

---

### 2. 审计日志清理

**执行模块**：审计模块

**频率**：每日 03:00

**流程**：

```sql
-- 物理删除已过 retention_until 的 minimal 级审计日志
DELETE FROM audit_logs
WHERE retention_until < NOW()
  AND level = 'minimal';

-- standard / full 级不自动物理删除，仅标记为 archived
UPDATE audit_logs
SET status = 'archived'
WHERE retention_until < NOW()
  AND level IN ('standard', 'full');
```

**归档**：被标记为 archived 的记录在月底批量写入冷存储（对象存储）。

---

### 3. Agent 使用统计汇总

**执行模块**：观测性模块

**频率**：每日 04:00

**输出**：

- 每个 Agent 的日活、请求量、错误率、P99 延迟
- 每个部门的 token 消耗汇总
- 全局模型调用分布（qwen3-32b / 14b / 8b 占比）

**存储**：写入 `daily_stats` 表，保留 365 天。

---

### 4. 备份完整性验证

**执行模块**：运维脚本

**频率**：每周日 01:00

**检查项**：

- [ ] PostgreSQL 全量备份文件可解压、可读取
- [ ] Redis RDB 文件可加载
- [ ] MinIO 中随机抽查 10 个 Skill Package 文件 hash 正确
- [ ] 备份文件大小与上周差异不超过 20%（异常增长检测）

**告警**：任一检查失败 → 钉钉 + 短信通知运维值班人员。

---

### 5. Salt 轮换

**执行模块**：安全模块

**频率**：每季度首月 1 日 00:00

**流程**：

```python
def rotate_salt():
    old_salt = k8s_secret.get("mau_salt")
    new_salt = generate_random_bytes(32)

    # 1. 写入新 salt
    k8s_secret.set("mau_salt_new", new_salt)

    # 2. 双 salt 并行期（90 天）
    #    - 新 user_id_hash 用新 salt 计算
    #    - 审计查询时同时尝试旧 salt 和新 salt

    # 3. 90 天后删除旧 salt
    k8s_secret.delete("mau_salt")
    k8s_secret.rename("mau_salt_new", "mau_salt")
```

**注意**：salt 轮换期间旧的审计记录仍可查询（双 salt 并行）。

---

### 6. 缓存预热

**执行模块**：Core 服务

**频率**：每 5 分钟

**流程**：

```python
def cache_warmup():
    # 根据过去 24 小时调用频率，预热 Top 20 热点 Agent
    hot_agents = stats.top_agents_by_calls(hours=24, limit=20)
    for agent_id in hot_agents:
        agent = db.get_agent(agent_id)
        redis.setex(f"agent:{agent_id}", 300, json.dumps(agent))
```

---

### 7. 会话过期清理

**执行模块**：Core 服务

**频率**：每 10 分钟

**流程**：

```python
def cleanup_expired_sessions():
    expired = db.query(
        "SELECT session_id, run_id FROM sessions WHERE expires_at < NOW()"
    )
    for session_id, run_id in expired:
        # 清除 Redis 中的会话数据
        redis.delete(f"session:{session_id}")
        redis.delete(f"runspec:{run_id}")
        redis.delete(f"pending:{session_id}")
        redis.delete(f"lock:session:{session_id}")

        # 数据库中标记为 expired（不删除，保留审计）
        db.execute(
            "UPDATE sessions SET status = 'expired' WHERE session_id = ?",
            session_id
        )
```

---

### 8. 模型健康探测

**执行模块**：模型网关

**频率**：每 10 秒

**流程**：

```python
def health_probe():
    for model in configured_models:
        try:
            response = http.get(model.health_endpoint, timeout=5)
            if response.status == 200:
                redis.setex(f"model:{model.id}:health", 10, "healthy")
            else:
                redis.setex(f"model:{model.id}:health", 10, "degraded")
        except Timeout:
            redis.setex(f"model:{model.id}:health", 10, "down")
```

---

### 9. 降级自动恢复检查

**执行模块**：降级控制模块

**频率**：每 1 分钟

**流程**：

```python
def check_degradation_recovery():
    current_level = int(redis.get("degradation:level") or 0)
    if current_level == 0:
        return

    # 检查所有触发指标是否连续 5 分钟低于阈值
    metrics_ok = check_all_metrics_below_threshold(duration=300)
    failure_rate_ok = check_user_failure_rate() < 0.01

    if metrics_ok and failure_rate_ok:
        new_level = max(0, current_level - 1)
        redis.set("degradation:level", str(new_level))
        redis.publish("degradation:changed", json.dumps({"level": new_level, "reason": "auto_recover"}))
```

---

### 10. 反馈数据汇总

**执行模块**：观测性模块

**频率**：每日 05:00

**输出**：

- 每个 Agent 的 👍 / 👎 数量及比率
- 👎 原因分布（Top 5）
- 按部门统计的用户满意度

**存储**：写入 `daily_feedback_stats` 表，供仪表盘展示。

### 11. 过期文件清理

**执行模块**：文档解析 Worker / 运维脚本

**频率**：每日 02:30

**流程**：

```python
def cleanup_expired_files():
    # 1. 查询数据库中 status=expired 或 expires_at < NOW() 的文件记录
    expired_files = db.query(
        "SELECT file_id, storage_path FROM file_uploads WHERE expires_at < NOW()"
    )
    for file_id, storage_path in expired_files:
        # 2. 从对象存储 temp/ 桶删除
        minio.delete(storage_path)
        # 3. 从数据库删除记录（或标记为 deleted）
        db.execute("DELETE FROM file_uploads WHERE file_id = ?", file_id)

    # 4. 兜底扫描：对象存储 temp/ 桶中超过 7 天且无数据库引用的文件
    orphan_files = minio.list("temp/", older_than_days=7)
    for obj in orphan_files:
        if not db.exists("SELECT 1 FROM file_uploads WHERE storage_path = ?", obj.path):
            minio.delete(obj.path)
```

---

### 12. Token 预算重置

**执行模块**：模型网关 / Core 服务

**频率**：每月 1 日 00:00

**流程**：

```python
def reset_token_budgets():
    next_month_start = date.today().replace(day=1) + timedelta(days=32)
    next_month_start = next_month_start.replace(day=1)
    next_month_end = (next_month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    # 1. 按 scope 聚合上月实际用量，写入历史统计表
    usage_stats = db.query("""
        SELECT scope, scope_id, used_tokens
        FROM token_quotas
        WHERE period_start = DATE_TRUNC('month', NOW() - INTERVAL '1 month')
    """)
    for scope, scope_id, used in usage_stats:
        db.execute("""
            INSERT INTO token_quota_history (scope, scope_id, period, used_tokens, created_at)
            VALUES (?, ?, ?, ?, NOW())
        """, scope, scope_id, period_start, used)

    # 2. 创建新周期配额记录（继承上月 budget_tokens，若配置变更则按新配置）
    active_quotas = db.query("""
        SELECT scope, scope_id, budget_tokens
        FROM token_quotas
        WHERE period_start = DATE_TRUNC('month', NOW() - INTERVAL '1 month')
    """)
    for scope, scope_id, budget in active_quotas:
        db.execute("""
            INSERT INTO token_quotas (scope, scope_id, budget_tokens, used_tokens, period_start, period_end)
            VALUES (?, ?, ?, 0, ?, ?)
            ON CONFLICT (scope, scope_id, period_start) DO NOTHING
        """, scope, scope_id, budget, next_month_start, next_month_end)

    # 3. 刷新 Redis 缓存中的用量计数器
    redis.delete("quota:*")
```

**注意**：
- 预算层级（platform / department / agent / user）在 `token_quotas` 表中独立管理
- 新周期记录采用 `ON CONFLICT DO NOTHING`，防止重复执行导致数据异常
- 历史用量写入 `token_quota_history` 表供长期分析和成本分摊

---

## 调度工具建议

| 方案 | 说明 | 推荐度 |
|------|------|--------|
| **APScheduler**（Python） | 与 FastAPI 同生态，集成简单 | ⭐⭐⭐ 推荐 |
| **Celery Beat** | 功能全，但需额外维护 Broker | ⭐⭐ 可选 |
| **K8s CronJob** | 独立于应用，适合重任务 | ⭐⭐ 适合备份、清理类任务 |
| **Linux crontab** | 最轻量，但无分布式协调 | ⭐ 不推荐 |

**推荐组合**：

- **应用内定时任务**（MAU 体检、缓存预热、健康探测）→ APScheduler
- **重资源 / 独立任务**（备份验证、审计清理）→ K8s CronJob
