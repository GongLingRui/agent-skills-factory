# 37. 生产环境部署 Checklist

> 版本：v0.6 · 2026-05-06

---

## 部署前检查

### 基础设施

- [ ] PostgreSQL 主从复制已配置，延迟监控就绪
- [ ] Redis 持久化已启用（AOF + RDB），主从已配置
- [ ] MinIO 版本控制（Versioning）已启用
- [ ] 对象存储桶 `agent-factory` 已创建，目录结构按 [22-data-archiving.md](22-data-archiving.md) 初始化
- [ ] 网络策略：widget 与 portal 域名已加入 ALLOWED_ORIGINS
- [ ] 负载均衡：Nginx/网关的 `proxy_read_timeout` 已调整为 >= 120s（SSE 兼容）

### 安全配置

- [ ] `JWT_SECRET` 已设置为 256 位随机字符串（K8s Secret 注入）
- [ ] `PORTAL_JWT_PUBLIC_KEY` 已配置（portal 公钥或 JWKS URL）
- [ ] short-lived JWT 的 `jti` 黑名单存储在 Redis（5 分钟 TTL）
- [ ] HTTPS 证书有效，HSTS 已启用
- [ ] CSP 策略已配置，禁止 `unsafe-inline` / `unsafe-eval`
- [ ] 后端 access log 已配置 token 参数 mask 规则
- [ ] MAU salt 已写入 K8s Secret，初始版本号已记录

### 模型集群

- [ ] 所有模型（qwen3-32b / 14b / 8b / bge-m3）健康端点返回 200
- [ ] 模型网关的 RPM/TPM 配额与模型实际能力匹配
- [ ] 模型 fallback 链路已验证（32b down → 14b → 8b）

---

## 部署步骤

### 第一阶段：数据库与种子数据

```bash
# 1. 执行 DDL（首次部署）
alembic upgrade head

# 2. 种子数据
python -m agent_factory init --auto

# 3. 验证
python -m agent_factory init --verify
```

### 第二阶段：配置检查

```bash
# 验证环境变量完整性
python -m agent_factory config check

# 预期输出：
# [OK] JWT_SECRET (长度 >= 32)
# [OK] DATABASE_URL 可连接
# [OK] REDIS_URL 可连接
# [OK] MINIO_BUCKET 可读写
# [OK] PORTAL_JWT_PUBLIC_KEY 可解析
```

### 第三阶段：服务启动顺序

1. **MinIO** → 对象存储就绪
2. **PostgreSQL** → 数据库就绪
3. **Redis** → 缓存 / 队列就绪
4. **Doc Worker** → 文档解析就绪
5. **Core 服务** → FastAPI 主服务
6. **API Gateway** → 入口网关
7. **Widget** → 前端静态资源
8. **Cron Job Pod** → 定时任务

### 第四阶段：功能验证

```bash
# 认证链路
curl -X POST https://agent.company.com/api/v1/auth/exchange \
  -H "Authorization: Bearer <portal-jwt>" \
  -d '{"agent_id": "contract-review-agent"}'

# Agent 列表
curl https://agent.company.com/api/v1/agents \
  -H "Cookie: session_id=..."

# 模型健康
curl https://agent.company.com/api/v1/health/models
```

---

## 部署后检查

### 监控与告警

- [ ] Prometheus 已抓取 `/metrics` 端点
- [ ] Grafana L0/L1/L2 仪表盘已导入
- [ ] 告警规则已生效（钉钉 webhook 测试通过）
- [ ] `af_degradation_level` gauge 显示为 0

### 审计与合规

- [ ] 发起一次测试对话，确认 `audit_logs` 表有 minimal 级记录写入
- [ ] 检查 `audit_logs` 当月分区已创建
- [ ] 验证 audit_log_stream 消费者组无积压：`redis-cli XINFO GROUPS audit_log_stream`

### 安全验证

- [ ] 从 URL 中移除 token 后刷新页面，确认 session cookie 独立工作
- [ ] 尝试用已使用的 short-lived JWT 调 `/auth/session`，确认返回 `TOKEN_REUSED`
- [ ] 尝试访问无权限的 Agent，确认返回 403
- [ ] 检查 access log 中 token 参数已被 mask

### 备份验证

- [ ] PostgreSQL WAL 归档已配置，PITR 恢复演练通过
- [ ] Redis RDB 定时备份任务已创建
- [ ] MinIO 版本控制已启用，删除测试文件后确认删除标记存在

---

## 首次上线后 24 小时内

- [ ] 检查 Grafana L0 仪表盘：QPS / P99 / 错误率是否在预期范围
- [ ] 检查 `degradation_events` 表：无意外自动降级触发
- [ ] 检查 `token_quotas` 表：用量累计正常
- [ ] 检查 feedback_logs：用户反馈正常写入
- [ ] 检查 cron job 执行日志：MAU 体检、会话清理、归档任务正常

---

## 回滚准备

| 场景 | 回滚操作 |
|------|---------|
| 新代码有 bug | K8s 滚动回滚到上一镜像版本 |
| 数据库迁移出错 | Alembic downgrade 到上一版本 |
| 配置错误 | 回滚 ConfigMap / Secret，重启 Pod |
| 模型集群故障 | 手动启用降级 `/admin/degradation/level`，切换 fallback 模型 |
| 严重安全事件 | 立即冻结所有 session（Redis FLUSHDB session:*），强制用户重新认证 |

---

## 相关文档

- 部署运维详细手册 → [18-deployment-ops.md](18-deployment-ops.md)
- 数据归档策略 → [22-data-archiving.md](22-data-archiving.md)
- 可观测性配置 → [32-observability-design.md](32-observability-design.md)
- 故障排查 → [36-troubleshooting.md](36-troubleshooting.md)
