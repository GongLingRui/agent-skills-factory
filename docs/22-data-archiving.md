# 22. 数据归档策略

> 版本：v0.6 · 2026-05-06

---

## 对象存储目录规范（MinIO / S3）

系统使用统一的 bucket（默认 `agent-factory`），内部按以下目录结构组织：

```
agent-factory/
├── skills/
│   └── {skill_id}/
│       └── {version}/
│           ├── SKILL.md
│           ├── enterprise.yaml
│           ├── references/
│           ├── schemas/
│           ├── scripts/
│           └── templates/
├── agents/
│   └── {agent_id}/
│       └── schemas/
│           └── {output_schema}.json          # Agent 级 schema 覆盖
├── temp/
│   └── {file_id}                              # 文档解析临时文件（TTL = session 过期）
├── archives/
│   ├── audit_logs/
│   │   └── {YYYY}/
│   │       └── {MM}/
│   │           └── audit_logs_YYYY-MM-DD.parquet
│   ├── feedback/
│   │   └── {YYYY}/
│   │       └── feedback_YYYY-Q{N}.parquet
│   └── daily_stats/
│       └── {YYYY}/
│           └── daily_stats_YYYY-MM.parquet
└── backups/
    └── {YYYY-MM-DD}/
        ├── pg_backup.sql.gz
        └── redis_rdb.tar.gz
```

**目录职责**：

| 目录 | 用途 | 生命周期 | 访问权限 |
|------|------|---------|---------|
| `skills/` | Skill Package 主存储 | 永不删除，仅标记 deprecated | Runner / Compiler / 管理后台 |
| `agents/` | Agent 级 schema 覆盖 | 随 Agent 版本更新 | Runner / 管理后台 |
| `temp/` | 文档解析结果、上传文件缓冲 | session 过期 + 7 天兜底清理 | Doc Worker / Runner |
| `archives/` | 审计日志、反馈、统计的归档文件 | 按合规策略（90 天 ~ 5 年） | 审计查询 / 运维 |
| `backups/` | 数据库全量备份、Redis RDB | 保留最近 30 天 + 每月 1 个长期保留 | 运维 |

---

## 归档范围

| 数据类型 | 热存储（在线） | 温存储（近线） | 冷存储（离线） | 物理删除 |
|----------|---------------|---------------|---------------|---------|
| Agent 配置 | PostgreSQL | - | - | 永不 |
| Skill Package | MinIO | - | - | 永不（标记 deprecated） |
| RunSpec | PostgreSQL + Redis | - | - | session 过期后 90 天 |
| Session 元数据 | PostgreSQL | - | - | 过期后 90 天 |
| 审计日志（minimal） | PostgreSQL | 对象存储（按月分区） | - | retention 到期后 |
| 审计日志（standard/full） | PostgreSQL | 对象存储（按月分区） | 磁带/冷盘（可选） | 5 年后 |
| MAU 元数据 | PostgreSQL | - | - | 90 天后 |
| 用户反馈 | PostgreSQL | 对象存储 | - | 2 年后 |
| 每日统计 | PostgreSQL | 对象存储 | - | 3 年后 |
| Checkpoint | Redis | - | - | session 过期即删 |

---

## 分层定义

### 热存储（Hot）

- **介质**：PostgreSQL 主库、Redis、MinIO
- **访问延迟**：< 10ms
- **保留期**：业务活跃期
- **查询方式**：实时 SQL / API

### 温存储（Warm）

- **介质**：MinIO / S3 对象存储（内网部署）
- **访问延迟**：100ms - 1s
- **保留期**：按合规要求（审计 90 天 ~ 5 年）
- **查询方式**：预签名 URL + 按日期前缀扫描

**归档格式**：

```
archives/
  audit_logs/
    2026/
      05/
        audit_logs_2026-05-01.parquet      # 按日分区，Parquet 压缩格式
        audit_logs_2026-05-02.parquet
  feedback/
    2026/
      feedback_2026-Q2.parquet             # 按季度汇总
```

**为什么选择 Parquet**：

- 列式存储，压缩率高（比 CSV 小 60-80%）
- 支持按列过滤查询，适合审计报表的聚合分析
- 企业内网常用工具（如 DuckDB、Pandas）可直接读取

### 冷存储（Cold）

- **介质**：磁带库 / 冷盘 / 异地备份中心
- **访问延迟**：小时级（需人工申请挂载）
- **保留期**：5 年以上（按央企档案管理规定）
- **查询方式**：需运维人员手动恢复

---

## 归档流程

### 审计日志归档（Minimal 级）

```
每日 03:00 cron 任务
  ↓
查询 audit_logs 表中 retention_until < NOW() 且 level = 'minimal' 的记录
  ↓
写入 parquet 文件：audit_logs_YYYY-MM-DD.parquet
  ↓
上传至 MinIO：archives/audit_logs/YYYY/MM/
  ↓
校验上传文件 hash 与本地一致
  ↓
从 PostgreSQL 物理删除已归档记录
  ↓
记录归档日志（归档时间、文件路径、记录数、hash）
```

### Standard / Full 级审计日志

这两级数据量小但合规价值高，采用更保守策略：

```
每月 1 日 02:00
  ↓
导出上月 standard/full 审计日志为 parquet
  ↓
上传至 MinIO 温存储
  ↓
保留 PostgreSQL 中最近 3 个月数据在线
  ↓
超过 3 个月的从 PostgreSQL 删除，仅保留温存储
  ↓
超过 5 年的温存储数据，经合规部门审批后转冷存储或物理删除
```

---

## 归档后查询

### 常规查询（热数据）

```sql
-- 直接查 PostgreSQL
SELECT * FROM audit_logs
WHERE agent_id = 'contract-review-agent'
  AND timestamp > NOW() - INTERVAL '7 days';
```

### 历史查询（已归档数据）

```python
# 应用层透明查询：先查热库，未命中则查温存储
def query_audit_logs(agent_id, start_date, end_date):
    # 1. 查热库
    hot_results = db.query(
        "SELECT * FROM audit_logs WHERE agent_id = ? AND timestamp BETWEEN ? AND ?",
        agent_id, start_date, end_date
    )

    # 2. 判断日期范围是否涉及已归档数据
    archived_dates = get_archived_dates_in_range(start_date, end_date)
    if archived_dates:
        # 从 MinIO 下载对应 parquet 文件
        parquet_files = minio.list(f"archives/audit_logs/{year}/{month}/")
        archived_results = duckdb.query(parquet_files, agent_id=agent_id)
        return merge_results(hot_results, archived_results)

    return hot_results
```

**注意**：归档数据查询耗时较长（秒级），API 应返回 `202 Accepted` + 轮询接口，避免阻塞。

---

## 容灾与恢复

### 归档数据损坏检测

每月校验：

```bash
# 计算 MinIO 中每个归档文件的 MD5，与归档日志比对
for file in $(minio ls archives/audit_logs/); do
    actual_md5=$(minio stat $file | grep ETag)
    expected_md5=$(cat archive_manifest.json | jq -r ".[\"$file\"].md5")
    if [ "$actual_md5" != "$expected_md5" ]; then
        alert "归档文件损坏: $file"
    fi
done
```

### 误删恢复

- MinIO 启用 **版本控制（Versioning）**：删除操作仅添加删除标记，数据物理保留 30 天
- PostgreSQL 通过 **WAL 归档 + PITR（Point-in-Time Recovery）** 支持任意时间点恢复
- Redis 通过 **RDB 快照 + AOF 持久化** 恢复：定期 RDB 备份（`redis_rdb.tar.gz`）用于全量恢复，AOF 用于增量回放（若启用）。Redis 不支持 WAL+PITR，恢复粒度为最近一次 RDB 快照
- 恢复操作需 **platform_admin + 安全团队双签审批**
