# 42. 灾难恢复设计

> 版本：v0.6 · 2026-05-06

---

## RTO/RPO 目标

| 场景 | RTO | RPO | 恢复方式 |
|------|-----|-----|---------|
| 单 Pod 故障 | <1 分钟 | 0 | K8s 自动重启 + 就绪探针 |
| 单节点故障 | <5 分钟 | 0 | K8s 自动调度到其他节点 |
| 数据库主库故障 | <10 分钟 | <1 分钟 | 自动 failover 到备库 |
| 全集群故障 | <30 分钟 | <5 分钟 | 切换到灾备集群（异地） |
| 数据误删 | <1 小时 | 按备份策略 | 从对象存储恢复快照 |
| 对象存储丢失 | <15 分钟 | 0 | 跨区域复制自动切换 |

---

## 备份策略

| 数据 | 备份方式 | 频率 | 保留期 | 存储位置 |
|------|---------|------|--------|---------|
| PostgreSQL | 全量物理备份（pg_basebackup） | 每日凌晨 02:00 | 30 天 | MinIO 备份桶 |
| PostgreSQL | WAL 归档 | 实时 | 7 天 | MinIO 备份桶 |
| PostgreSQL | 逻辑备份（pg_dump 关键表） | 每 6 小时 | 7 天 | MinIO 备份桶 |
| Redis | RDB 持久化 | 每 6 小时 | 7 天 | MinIO 备份桶 |
| MinIO | 跨区域复制 | 实时 | - | 异地 MinIO 集群 |
| Skill Package | Git + 对象存储 | 每次更新 | 永久 | Git + MinIO |
| 配置 | Git 版本管理 | 每次变更 | 永久 | Git |

---

## 数据库故障恢复

### 主库故障

```
监控探测主库无响应（连续 3 次失败）
  ↓
自动 failover（Patroni / repmgr）
  ↓
备库提升为主库
  ↓
更新 K8s Service endpoint
  ↓
告警通知（钉钉 + 短信）
  ↓
原主库恢复后作为新备库加入
```

### 数据误删恢复

```bash
# 1. 确定恢复时间点（T-1 小时前的全量备份 + WAL）
# 2. 新建临时实例
pg_basebackup -D /tmp/recovery -X stream -P
# 3. 应用 WAL 到指定时间点
pg_waldump ...
# 4. 导出需要恢复的数据
pg_dump -t audit_logs ...
# 5. 导入生产库
psql -d agent_factory < recovery.sql
```

---

## 全集群灾难恢复

### 异地灾备架构

```
┌─────────────────┐                      ┌─────────────────┐
│   生产集群       │    实时同步           │   灾备集群       │
│  (Region A)     │  ──────────────────▶ │  (Region B)     │
│                 │   PG 流复制 +         │                 │
│  PG 主库        │   MinIO 跨区域复制    │  PG 备库        │
│  Redis 主从     │                      │  Redis 主从     │
│  MinIO 主集群   │                      │  MinIO 从集群   │
└─────────────────┘                      └─────────────────┘
```

### 切换流程

```bash
# 1. 确认生产集群不可用（人工 + 自动双重确认）
# 2. DNS 切换到灾备集群（内网 DNS 方案，如 CoreDNS / BIND / 企业自研 DNS）
# 示例：通过内部 DNS API 修改 A 记录指向灾备集群 ingress
curl -X POST http://dns.internal/api/v1/records \
  -H "Authorization: Bearer $DNS_ADMIN_TOKEN" \
  -d '{"zone":"agent.company.com","name":"@","type":"A","value":"10.x.x.x"}'

# 3. 提升灾备 PG 为读写
patronictl failover agent-factory-pg --candidate pg-dr-1

# 4. 启动灾备 Core 服务
kubectl scale deployment agent-factory-core --replicas=3 -n agent-factory-dr

# 5. 验证服务可用性
./scripts/smoke-test.sh https://dr.agent.company.com

# 6. 通知业务部门
```

---

## 定期演练

| 演练类型 | 频率 | 内容 |
|---------|------|------|
| 数据库 failover | 每月 | 手动触发 Patroni failover，验证自动切换 |
| 备份恢复 | 每季度 | 从备份恢复测试实例，验证数据完整性 |
| 全集群切换 | 每半年 | 异地灾备演练，验证 RTO/RPO |
| 数据误删 | 每年 | 模拟误删审计日志，验证 PITR 恢复 |

---

## 与现有文档的衔接

- **备份策略** → [18-deployment-ops.md](18-deployment-ops.md) §备份策略
- **部署拓扑** → [18-deployment-ops.md](18-deployment-ops.md) §部署拓扑
- **监控告警** → [32-observability-design.md](32-observability-design.md)
