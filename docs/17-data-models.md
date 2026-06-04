# 17. 数据模型与 Schema

> 版本：v0.6 · 2026-05-06

---

## 核心实体关系

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  User       │────<│  Agent App  │────>│  Skill      │
│  (用户)      │     │  (Agent应用) │     │  (技能包)    │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │   RunSpec   │
                    │  (运行规格)  │
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │   Session   │
                    │   (会话)    │
                    └─────────────┘
```

---

## Agent App 数据模型

```yaml
agent_app:
  id: string PK                    # contract-review-agent
  name: string                     # 合同审查助手
  description: string
  version: string                  # semver
  runspec_schema_version: int      # 默认 1
  owner: string                    # legal-department
  lifecycle_state: enum            # active / cold / archived

  release:
    strategy: enum                 # full / canary / pinned
    canary_percent: int            # 0-100
    canary_departments: [string]   # 灰度目标部门
    canary_target_users: [string]  # 灰度目标用户白名单（可选）
    pinned_version: string         # 回滚版本

  model_policy:
    default: string                # qwen3-32b
    fallback: string               # qwen3-14b
    low_cost: string               # qwen3-8b

  skill:
    id: string FK                  # clause-review
    version_pin: string            # semver range

  tools_allow: [string]            # 工具白名单
  knowledge_scopes: [string]       # 知识范围
  output_schema: string            # 输出 schema 名称

  limits:
    max_turns: int
    max_tokens: int
    timeout_seconds: int

  concurrency:
    class: enum                    # interactive / document / batch / privileged
    queue_priority: int            # 1-10

  degradation_exempt: bool         # 是否豁免全局降级（默认 false，仅 platform_admin 可改）

  audit:
    level: enum                    # minimal / standard / full
    trace_prompt: bool
    trace_tool_calls: bool
    trace_retrieval_ids: bool
    retain_days: int

  enterprise_config: jsonb          # 企业治理扩展，详见下方 JSON Schema
  tags: jsonb                       # 标签数组 [legal, contract, risk]
  ui_config: jsonb                 # 前端渲染配置

  created_at: timestamp
  updated_at: timestamp
  created_by: string
```

**关于 `enterprise_config.mau_threshold`**：

- 默认值 5（30 天内少于 5 个不同用户使用则进入 cold）
- 业务部门可在 agent.yaml 的 `enterprise.mau_threshold` 中自定义
- 该字段影响 MAU 体检 cron 任务的行为（详见 [21-cron-jobs.md](21-cron-jobs.md)）

---

## Agent App YAML → DB 字段映射表

| YAML 字段 | DB 字段 | 说明 |
|-----------|---------|------|
| `id` | `id` | 主键，完全一致 |
| `name` | `name` | 完全一致 |
| `version` | `version` | 完全一致 |
| `runspec_schema_version` | `runspec_schema_version` | 完全一致 |
| `owner` | `owner` | 完全一致 |
| `lifecycle_state` | `lifecycle_state` | 完全一致 |
| `release` | `release_config` | JSONB 对象 |
| `model_policy` | `model_policy` | JSONB 对象 |
| `skill` | `skill_config` | JSONB 对象（含 id / version_pin） |
| `tools.allow` | `tools_allow` | JSONB 数组 |
| `knowledge_scopes` | `knowledge_scopes` | JSONB 数组 |
| `output_schema` | `output_schema` | 完全一致 |
| `limits` | `limits_config` | JSONB 对象 |
| `concurrency` | `concurrency_config` | JSONB 对象 |
| `degradation_exempt` | `degradation_exempt` | BOOLEAN，默认 false |
| `audit` | `audit_config` | JSONB 对象 |
| `enterprise` | `enterprise_config` | JSONB 对象 |
| `tags` | `tags` | JSONB 数组 |
| `ui_config` | `ui_config` | JSONB 对象 |
| `instruction` | `instruction` | TEXT 类型，YAML 中无此字段时存 NULL |

**命名约定**：根级对象/映射在 DB 中以 `_config` 后缀命名，数组和简单字段保持原名。

---

## `enterprise_config` JSON Schema

```json
{
  "type": "object",
  "properties": {
    "risk_tier": { "type": "string", "enum": ["low", "medium", "high"] },
    "compliance_checklist": { "type": "array", "items": { "type": "string" } },
    "mau_threshold": { "type": "integer", "default": 5, "minimum": 1 }
  },
  "required": ["risk_tier"]
}
```

- `risk_tier`：风险等级，影响 Skill Compiler 注入的治理指令
- `compliance_checklist`：合规检查项列表，Agent 上线前逐项确认
- `mau_threshold`：30 天 MAU 体检阈值，低于则转入 cold（默认值 5）

---

## Skill Package 数据模型

```yaml
skill:
  id: string PK                    # clause-review
  version: string PK               # 0.1.0（联合主键）
  name: string                     # clause-review
  description: string
  when_to_use: string

  owner: string                    # legal-department
  risk_tier: enum                  # low / medium / high

  skill_package_hash: string       # sha256
  storage_path: string             # 对象存储路径

  status: enum                     # active / deprecated
  deprecated_at: timestamp
  deprecated_by: string

  created_at: timestamp
  created_by: string
```

---

## Tool 数据模型

```yaml
tool:
  id: string PK                    # kb.search
  version: string                  # 1.0.0
  name: string
  description: string

  input_schema: jsonb              # JSON Schema
  output_schema: jsonb             # JSON Schema

  permission_required: [string]    # 所需权限列表

  timeout_seconds: int
  rate_limit:
    per_user: int                  # 每分钟
    per_agent: int
    global: int

  implementation:
    type: enum                     # http_api / controlled_script / internal_function / mcp
    endpoint: string               # HTTP URL 或函数路径
    script_id: string              # controlled_script 时关联
    mcp_server_id: string          # mcp 类型时关联 MCP Server ID
    mcp_tool_name: string          # mcp 类型时关联 MCP 工具名

  status: enum                     # active / disabled
  created_at: timestamp
  updated_at: timestamp
```

**说明**：`implementation.type` 新增 `mcp` 类型，用于接入外部 MCP Server（详见 [09-tool-gateway.md](09-tool-gateway.md) §MCP 工具接入）。

---

## RunSpec 数据模型（运行时）

```yaml
run_spec:
  run_id: string PK                # run_20260506_001
  runspec_schema_version: int      # 1

  agent_id: string FK
  agent_version: string

  skill_id: string FK
  skill_version: string
  skill_package_hash: string

  user_id_hash: string             # SHA-256(user_id + salt)，不存明文 user_id
  department: string

  prompt_parts: jsonb              # [{role, content}, ...]
  lazy_references: jsonb           # [{name, path}, ...]
  indexed_references: jsonb        # [{name, scope}, ...]

  allowed_tools: [string]
  retrieval_scopes: [string]

  script_hooks: jsonb              # {preprocess: [...]}
  output_schema: string

  runtime: jsonb                   # {model, fallback_model, max_turns, timeout_seconds, max_tokens}
  audit: jsonb                     # {level, trace_prompt, ...}

  created_at: timestamp
  expires_at: timestamp            # session 过期时间
```

---

## Session 数据模型（运行时）

```yaml
session:
  session_id: string PK
  run_id: string FK                # 关联 RunSpec

  user_id_hash: string             # SHA-256(user_id + salt)，不存明文 user_id
  agent_id: string
  department: string

  status: enum                     # created / running / completed / error / timeout / expired

  turn_count: int                  # 当前轮数
  total_tokens: int                # 累计 token

  created_at: timestamp
  last_activity: timestamp
  expires_at: timestamp
```

---

## Checkpoint 数据模型（运行时 + 归档）

```yaml
checkpoint:
  checkpoint_id: string PK
  run_id: string FK
  session_id: string FK

  turn_number: int                 # 第几轮完成后存的档
  timestamp: timestamp

  messages: jsonb                  # 截至当前的完整消息历史
  token_count: int                 # 当前累计 token
  tool_calls_so_far: jsonb         # 已完成的工具调用记录

  created_at: timestamp
```

**存储策略**：

| 场景 | 存储位置 | TTL |
|------|---------|-----|
| 活跃会话 checkpoint | Redis（Hash） | session 过期时间 |
| 已结束会话 checkpoint | PostgreSQL | audit.retain_days |
| 浏览器端恢复用 | IndexedDB（widget 缓存最近 1 个） | 30 天 |

---

## 审计日志数据模型

```yaml
audit_log:
  id: bigint PK auto_increment
  run_id: string
  session_id: string

  timestamp: timestamp
  level: enum                      # minimal / standard / full

  # minimal 级必录
  user_id_hash: string             # SHA-256(user_id + salt)
  agent_id: string
  department: string
  tool_calls: jsonb                # [{tool_id, params, result, latency_ms}]
  token_count: int
  cost: float                      # 估算成本
  error_code: string
  retrieval_ids: [string]          # 检索命中文档 ID

  # standard 级追加
  prompt_summary: string           # prompt 前 200 字摘要
  retrieval_hits: jsonb            # 命中详情

  # full 级追加
  full_prompt: text
  full_output: text

  retention_until: timestamp       # 按 audit.retain_days 计算
  status: enum                     # active / archived
```

**说明**：`status` 字段用于归档标记。minimal 级超 retention 后物理删除；standard/full 级先标记 archived，再按月归档到对象存储（详见 [22-data-archiving.md](22-data-archiving.md)）。

---

## 用户反馈数据模型

```yaml
feedback_log:
  id: bigint PK auto_increment
  session_id: string
  message_id: string
  run_id: string
  agent_id: string

  feedback: enum                   # thumbs_up / thumbs_down
  reasons: [string]                # 原因标签（如 inaccurate, wrong_citation）
  comment: string                  # 用户文字反馈（最多 200 字）

  timestamp: timestamp
```

---

## MAU 元数据模型

```yaml
agent_usage_log:
  id: bigint PK auto_increment
  user_id_hash: string             # SHA-256(user_id + salt)
  agent_id: string
  date: date                       # 只到日
  count: int                       # 当日使用次数

  retention_until: timestamp       # 90 天后归档
```

---

## Token 预算数据模型

```yaml
token_quota:
  id: bigint PK auto_increment
  scope: enum                      # platform / department / agent / user
  scope_id: string                 # 对应 scope 的标识（如 department=legal, agent_id=xxx, user_id=xxx）

  budget_tokens: bigint            # 预算 token 数（月度）
  used_tokens: bigint              # 已用 token 数
  period_start: date               # 周期开始日
  period_end: date                 # 周期结束日

  created_at: timestamp
  updated_at: timestamp
```

**预算层级**：

```
平台总预算（platform）
  ├─→ 部门预算（department）
  │     ├─→ Agent 预算（agent）
  │     │     └─→ 用户预算（user，可选）
```

**超限动作**详见 [10-model-gateway.md](10-model-gateway.md) §Token 预算。

---

## 文件上传临时数据模型

```yaml
file_upload:
  file_id: string PK               # UUID
  session_id: string FK
  user_id_hash: string             # SHA-256(user_id + salt)，不存明文 user_id

  name: string                     # 原始文件名
  size: bigint                     # 文件大小（字节）
  mime_type: string                # 文件类型
  storage_path: string             # 对象存储临时路径（如 minio://temp/files/xxx）

  status: enum                     # pending / extracted / expired / deleted
  extracted_text_path: string      # 文档解析后的文本存储路径（对象存储 temp/ 桶）

  created_at: timestamp
  expires_at: timestamp            # 默认 session 过期时间
```

**存储策略**：

- 敏感文件（合同/公文）**不写磁盘**，直接流入内存缓冲区或直传文档解析服务
- 解析结果临时存入对象存储的 `temp/` 桶，路径记录在 `extracted_text_path`，**不写入 PostgreSQL**
- session 过期后对象存储自动清理，`file_id` 仅在当前 session 内有效
- PostgreSQL 只保留元数据（文件名、大小、状态），**绝不保留文件内容或解析后文本**

---

## 每日统计汇总数据模型

```yaml
daily_stats:
  id: bigint PK auto_increment
  date: date

  agent_id: string                 # 空字符串表示"全平台汇总"
  department: string               # 空字符串表示"全部门汇总"

  request_count: int               # 请求次数
  error_count: int                 # 错误次数
  p99_latency_ms: int              # P99 延迟

  token_input: bigint              # 输入 token
  token_output: bigint             # 输出 token
  model_distribution: jsonb        # { "qwen3-32b": 60%, "qwen3-14b": 30%, ... }

  created_at: timestamp
```

---

## 配置变更审计日志数据模型

记录 `system_config`、`platform_policies`、`org_policies` 的所有写操作，满足合规追溯要求。

```yaml
config_change_log:
  id: bigint PK auto_increment
  table_name: string               # system_config / platform_policies / org_policies
  record_id: string                # 被修改记录的标识。system_config 时为 key；platform_policies / org_policies 时为 lineage_id
  action: enum                     # create / update / delete

  old_value: jsonb                 # 变更前的完整值（delete 时非空）
  new_value: jsonb                 # 变更后的完整值（create 时非空）
  change_reason: string            # 变更原因（管理后台强制填写）

  operator_id: string              # 操作人 user_id
  operator_ip: string              # 操作来源 IP
  timestamp: timestamp

  created_at: timestamp
```

**索引**：`table_name + record_id + timestamp`（用于按配置项追溯历史）。

---

## 降级事件数据模型

记录每一次降级级别变更（自动触发或手动操作），用于故障复盘和合规审计。

```yaml
degradation_event:
  id: bigint PK auto_increment
  level: int                       # 变更后的降级级别 0~6
  previous_level: int              # 变更前的级别

  trigger: enum                    # manual / auto_cpu / auto_memory / auto_model / auto_error_rate / auto_queue_latency
  reason: string                   # 人工填写的理由（manual 时必填）
  operator_id: string              # 操作人（auto 触发时为 system）

  metrics_snapshot: jsonb          # 触发时的关键指标快照（如 queue_p99_ms, error_rate, cpu_percent）

  started_at: timestamp            # 降级生效时间
  recovered_at: timestamp          # 恢复时间（null 表示尚未恢复）
  expected_duration_minutes: int   # 预期持续时间（manual 时填写）

  created_at: timestamp
```

**索引**：`started_at DESC`（用于仪表盘展示最近事件）。

---

## Token 预算调整历史数据模型

记录每一次预算额度变更，用于财务对账和审计。

```yaml
token_quota_history:
  id: bigint PK auto_increment
  scope: enum                      # platform / department / agent / user
  scope_id: string

  previous_budget: bigint          # 调整前预算
  new_budget: bigint               # 调整后预算
  change_reason: string            # 调整原因

  effective_period: string         # 生效周期（YYYY-MM）
  effective_immediately: bool      # 是否立即生效（false = 下月生效）

  operator_id: string              # 操作人
  timestamp: timestamp

  created_at: timestamp
```

---

## 每日反馈汇总数据模型

按日聚合用户反馈数据，供运营仪表盘快速查询，避免直接扫描 `feedback_logs` 大表。

```yaml
daily_feedback_stat:
  id: bigint PK auto_increment
  date: date
  agent_id: string

  total_messages: int              # 当日该 Agent 总消息数
  feedback_up: int                 # thumbs_up 数量
  feedback_down: int               # thumbs_down 数量
  feedback_rate: float             # 有反馈的消息占比

  reason_distribution: jsonb       # { "inaccurate": 5, "wrong_citation": 3, ... }

  created_at: timestamp

  UNIQUE (date, agent_id)
```

**生成方式**：每日 04:00 cron 任务从 `feedback_logs` 聚合生成，写入后不再变更。

---

## 归档清单数据模型

记录每一次归档操作的元数据，用于完整性校验和生命周期管理。

```yaml
archive_manifest:
  id: bigint PK auto_increment
  archive_type: enum               # audit_logs / feedback / daily_stats
  file_path: string                # 对象存储中的完整路径
  file_size_bytes: bigint
  record_count: bigint             # 归档文件包含的记录数
  date_range_start: date           # 归档数据起始日
  date_range_end: date             # 归档数据结束日

  checksum_md5: string             # 文件 MD5
  checksum_sha256: string          # 文件 SHA-256

  archived_at: timestamp
  archived_by: string              # 通常是 cron 任务 ID
  verified_at: timestamp           # 完整性校验时间
  deleted_at: timestamp            # 物理删除时间（合规到期后）

  created_at: timestamp
```

**索引**：`archive_type + date_range_start`（用于按日期范围定位归档文件）。

---

## 枚举值定义

### lifecycle_state

| 值 | 说明 |
|----|------|
| active | 正常运行 |
| cold | 低 MAU 被归档（也称 deprecated），从推荐位下架 |
| archived | 已废弃，完全不可访问 |

**状态转换**：

```
active ←──(MAU 体检不达标)──→ cold
  ↑                            │
  └──(重新评测通过)─────────────┘

active / cold ──(业务部门申请废弃 / cold 超 90 天自动归档)──→ archived
```

### release.strategy

| 值 | 说明 |
|----|------|
| full | 全量发布 |
| canary | 灰度发布 |
| pinned | 固定版本（回滚用） |

### concurrency.class

| 值 | 说明 |
|----|------|
| interactive | 交互式，低延迟 |
| document | 文档处理，中等延迟 |
| batch | 批量任务，可排队 |
| privileged | 最高优先级 |

### audit.level

| 值 | 说明 |
|----|------|
| minimal | 最小审计（默认） |
| standard | 标准审计 |
| full | 完整审计 |

### session.status

| 值 | 说明 |
|----|------|
| created | 已创建，等待输入 |
| running | 执行中 |
| completed | 已完成 |
| error | 发生错误 |
| timeout | 超时 |
| expired | 会话已过期（清理后状态） |

---

## 数据库表设计建议

```sql
-- Agent App 表
CREATE TABLE agent_apps (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    version VARCHAR(32) NOT NULL,
    runspec_schema_version INT DEFAULT 1,
    owner VARCHAR(64),
    lifecycle_state VARCHAR(16) DEFAULT 'active',
    release_config JSONB,
    model_policy JSONB,
    skill_config JSONB,
    tools_allow JSONB,
    knowledge_scopes JSONB,
    output_schema VARCHAR(64),
    limits_config JSONB,
    concurrency_config JSONB,
    audit_config JSONB,
    enterprise_config JSONB,
    tags JSONB,
    ui_config JSONB,
    degradation_exempt BOOLEAN DEFAULT false,  -- Agent 级降级豁免（仅 platform_admin 可改）
    cold_since TIMESTAMP,                 -- 进入冷态的时间（retention gate 标记）
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(64)
);

-- Agent 历史版本表（保留最近 10 个版本，持久化存储）
CREATE TABLE agent_versions (
    agent_id VARCHAR(64) NOT NULL,
    version VARCHAR(32) NOT NULL,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    instruction TEXT,                     -- Agent 核心指令（agent.yaml instruction 字段快照）
    release_config JSONB,
    model_policy JSONB,
    skill_config JSONB,
    tools_allow JSONB,
    knowledge_scopes JSONB,
    output_schema VARCHAR(64),
    limits_config JSONB,
    concurrency_config JSONB,
    audit_config JSONB,
    enterprise_config JSONB,
    tags JSONB,
    ui_config JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(64),
    PRIMARY KEY (agent_id, version)
);

-- Skill 表
CREATE TABLE skills (
    id VARCHAR(64),
    version VARCHAR(32),
    name VARCHAR(128),
    description TEXT,
    when_to_use TEXT,
    owner VARCHAR(64),
    risk_tier VARCHAR(16),
    skill_package_hash VARCHAR(64),
    storage_path VARCHAR(256),
    status VARCHAR(16) DEFAULT 'active',
    deprecated_at TIMESTAMP,
    deprecated_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(64),
    PRIMARY KEY (id, version)
);

-- Tool 表
CREATE TABLE tools (
    id VARCHAR(64) PRIMARY KEY,
    version VARCHAR(32),
    name VARCHAR(128),
    description TEXT,
    input_schema JSONB,
    output_schema JSONB,
    permission_required JSONB,
    timeout_seconds INT,
    rate_limit JSONB,
    implementation JSONB,
    status VARCHAR(16) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- RunSpec 表（运行时，可存 Redis 或临时表）
CREATE TABLE run_specs (
    run_id VARCHAR(64) PRIMARY KEY,
    runspec_schema_version INT,
    agent_id VARCHAR(64),
    agent_version VARCHAR(32),
    skill_id VARCHAR(64),
    skill_version VARCHAR(32),
    skill_package_hash VARCHAR(64),
    skill_file_manifest JSONB,            -- 包内各文件 sha256 映射表，运行时按需拉取做精确校验
    user_id_hash VARCHAR(64) NOT NULL,     -- SHA-256(user_id + salt)，不存明文
    department VARCHAR(64),
    prompt_parts JSONB,
    lazy_references JSONB,
    indexed_references JSONB,
    allowed_tools JSONB,
    retrieval_scopes JSONB,
    script_hooks JSONB,
    output_schema VARCHAR(64),
    runtime JSONB,
    audit JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- Session 表
CREATE TABLE sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    user_id_hash VARCHAR(64) NOT NULL,     -- SHA-256(user_id + salt)，不存明文
    agent_id VARCHAR(64) NOT NULL,
    department VARCHAR(64),
    status VARCHAR(16) DEFAULT 'created',
    turn_count INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    last_activity TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);
CREATE INDEX idx_sessions_user ON sessions(user_id_hash, created_at DESC);
CREATE INDEX idx_sessions_agent ON sessions(agent_id, created_at DESC);

-- Checkpoint 表（已结束会话的 checkpoint 归档）
CREATE TABLE checkpoints (
    checkpoint_id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    turn_number INT NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    messages JSONB,
    token_count INT,
    tool_calls_so_far JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_checkpoints_session ON checkpoints(session_id, turn_number);

-- 审计日志表（按日期分区）
CREATE TABLE audit_logs (
    id BIGSERIAL,
    run_id VARCHAR(64),
    session_id VARCHAR(64),
    timestamp TIMESTAMP DEFAULT NOW(),
    level VARCHAR(16),
    user_id_hash VARCHAR(64),
    agent_id VARCHAR(64),
    department VARCHAR(64),
    tool_calls JSONB,
    token_count INT,
    cost FLOAT,
    error_code VARCHAR(32),
    retrieval_ids JSONB,
    prompt_summary TEXT,
    retrieval_hits JSONB,
    full_prompt TEXT,
    full_output TEXT,
    retention_until TIMESTAMP,
    status VARCHAR(16) DEFAULT 'active',
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- 审计日志常用索引（分区表上建 LOCAL 索引）
CREATE INDEX idx_audit_agent_time ON audit_logs(agent_id, timestamp);
CREATE INDEX idx_audit_run_id ON audit_logs(run_id);

-- 按月自动创建分区（部署后执行或放入初始化脚本）
-- 示例：创建 2026-05 至 2026-12 的分区
CREATE TABLE audit_logs_2026_05 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE audit_logs_2026_06 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
-- 后续月份由 cron 任务或管理脚本自动创建：
-- SELECT create_audit_partition(NEXT_MONTH);

-- MAU 元数据表
CREATE TABLE agent_usage_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id_hash VARCHAR(64),
    salt_version VARCHAR(8),              -- 哈希盐版本（支持盐轮换）
    agent_id VARCHAR(64),
    date DATE,
    count INT DEFAULT 1,
    retention_until TIMESTAMP
);
CREATE INDEX idx_agent_usage ON agent_usage_logs(agent_id, date);

-- 用户反馈表
CREATE TABLE feedback_logs (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64),
    message_id VARCHAR(64),
    run_id VARCHAR(64),
    agent_id VARCHAR(64),
    feedback VARCHAR(16),
    reasons JSONB,
    comment TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_feedback_agent ON feedback_logs(agent_id, timestamp);

-- Token 预算表
CREATE TABLE token_quotas (
    id BIGSERIAL PRIMARY KEY,
    scope VARCHAR(16) NOT NULL,           -- platform / department / agent / user
    scope_id VARCHAR(64) NOT NULL,
    budget_tokens BIGINT NOT NULL,
    used_tokens BIGINT DEFAULT 0,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (scope, scope_id, period_start)
);

-- 文件上传临时表
CREATE TABLE file_uploads (
    file_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    user_id_hash VARCHAR(64) NOT NULL,     -- SHA-256(user_id + salt)，不存明文
    file_name VARCHAR(256) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(64) NOT NULL,
    sha256 VARCHAR(64) NOT NULL,           -- 文件内容 sha256，用于秒传去重
    storage_path VARCHAR(512),            -- 原始文件临时路径（对象存储 temp/ 桶）
    status VARCHAR(16) DEFAULT 'pending',
    extracted_text_path VARCHAR(512),     -- 解析后文本路径（对象存储 temp/ 桶），不存内容
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);
CREATE INDEX idx_file_uploads_session ON file_uploads(session_id);
CREATE INDEX idx_file_uploads_sha256 ON file_uploads(sha256);

-- 每日统计表
CREATE TABLE daily_stats (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    agent_id VARCHAR(64) DEFAULT '',
    department VARCHAR(64) DEFAULT '',
    request_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    p99_latency_ms INT,
    token_input BIGINT DEFAULT 0,
    token_output BIGINT DEFAULT 0,
    model_distribution JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (date, agent_id, department)
);

-- RBAC 角色表
CREATE TABLE roles (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- RBAC 权限表
CREATE TABLE permissions (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    resource VARCHAR(32) NOT NULL,    -- agent / skill / tool / audit
    action VARCHAR(16) NOT NULL       -- read / write / admin
);

-- 角色-权限关联
CREATE TABLE role_permissions (
    role_id VARCHAR(32) REFERENCES roles(id),
    permission_id VARCHAR(32) REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);

-- 用户-角色关联（按部门隔离）
CREATE TABLE user_roles (
    user_id_hash VARCHAR(64),             -- SHA-256(user_id + salt)，不存明文 user_id；portal 同步时由网关层转换
    role_id VARCHAR(32) REFERENCES roles(id),
    department VARCHAR(64),
    granted_by VARCHAR(64),               -- 授权者 user_id_hash
    granted_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id_hash, role_id, department)
);

-- 平台策略配置（系统级铁律）
CREATE TABLE platform_policies (
    lineage_id VARCHAR(32) NOT NULL,      -- 策略概念 ID（如 platform_base）
    version INT NOT NULL,
    prompt TEXT NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (lineage_id, version)
);

-- 部门策略配置
CREATE TABLE org_policies (
    lineage_id VARCHAR(32) NOT NULL,      -- 策略概念 ID（如 legal_policy）
    department VARCHAR(64) NOT NULL,
    version INT NOT NULL,
    prompt TEXT NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (lineage_id, version),
    UNIQUE (department, lineage_id, version)
);

-- 生效策略查询视图（每个部门取 enabled=true 且 version 最大的策略）
-- 应用层等价 SQL：
-- SELECT DISTINCT ON (department) * FROM org_policies
-- WHERE enabled = true ORDER BY department, version DESC;

-- 配置变更审计日志表
CREATE TABLE config_change_logs (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(64) NOT NULL,      -- system_config / platform_policies / org_policies
    record_id VARCHAR(64) NOT NULL,       -- 被修改记录的标识
    action VARCHAR(16) NOT NULL,          -- create / update / delete
    old_value JSONB,
    new_value JSONB,
    change_reason TEXT,
    operator_id VARCHAR(64) NOT NULL,
    operator_ip VARCHAR(64),
    timestamp TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_config_change_table_record ON config_change_logs(table_name, record_id, timestamp);

-- 降级事件表
CREATE TABLE degradation_events (
    id BIGSERIAL PRIMARY KEY,
    level INT NOT NULL,
    previous_level INT NOT NULL,
    trigger VARCHAR(32) NOT NULL,         -- manual / auto_cpu / auto_memory / auto_model / auto_error_rate / auto_queue_latency
    reason TEXT,
    operator_id VARCHAR(64),              -- auto 触发时为 system
    metrics_snapshot JSONB,
    started_at TIMESTAMP NOT NULL,
    recovered_at TIMESTAMP,
    expected_duration_minutes INT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_degradation_started ON degradation_events(started_at DESC);

-- Token 预算调整历史表
CREATE TABLE token_quota_history (
    id BIGSERIAL PRIMARY KEY,
    scope VARCHAR(16) NOT NULL,
    scope_id VARCHAR(64) NOT NULL,
    previous_budget BIGINT,
    new_budget BIGINT NOT NULL,
    change_reason TEXT,
    effective_period VARCHAR(7) NOT NULL, -- YYYY-MM
    effective_immediately BOOLEAN DEFAULT true,
    operator_id VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_quota_history_scope ON token_quota_history(scope, scope_id, timestamp DESC);

-- 每日反馈汇总表
CREATE TABLE daily_feedback_stats (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    agent_id VARCHAR(64) NOT NULL,
    total_messages INT DEFAULT 0,
    feedback_up INT DEFAULT 0,
    feedback_down INT DEFAULT 0,
    feedback_rate FLOAT DEFAULT 0,
    reason_distribution JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (date, agent_id)
);
CREATE INDEX idx_daily_feedback_agent ON daily_feedback_stats(agent_id, date DESC);

-- 归档清单表
CREATE TABLE archive_manifests (
    id BIGSERIAL PRIMARY KEY,
    archive_type VARCHAR(32) NOT NULL,    -- audit_logs / feedback / daily_stats
    file_path VARCHAR(512) NOT NULL,
    file_size_bytes BIGINT,
    record_count BIGINT,
    date_range_start DATE NOT NULL,
    date_range_end DATE NOT NULL,
    checksum_md5 VARCHAR(32),
    checksum_sha256 VARCHAR(64),
    archived_at TIMESTAMP NOT NULL,
    archived_by VARCHAR(64),
    verified_at TIMESTAMP,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_manifest_type_date ON archive_manifests(archive_type, date_range_start);

-- 安全事件表（Prompt 注入等安全威胁记录）
CREATE TABLE security_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(32) NOT NULL,      -- PROMPT_INJECTION_ATTEMPT / UNAUTHORIZED_ACCESS / etc.
    user_id_hash VARCHAR(64),             -- 触发者身份哈希
    agent_id VARCHAR(64),
    session_id VARCHAR(64),
    input_summary TEXT,                   -- 输入前 200 字符（脱敏）
    trigger_rule VARCHAR(64),             -- 匹配到的规则名
    queue_priority_before INT,            -- 触发前的优先级
    queue_priority_after INT,             -- 触发后的优先级
    timestamp TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_security_events_user ON security_events(user_id_hash, timestamp);
CREATE INDEX idx_security_events_type ON security_events(event_type, timestamp);

-- 系统配置表
CREATE TABLE system_configs (
    key VARCHAR(128) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(64)
);
```

---

## 索引设计 rationale

### Agent App 表

```sql
CREATE INDEX idx_agent_apps_owner ON agent_apps(owner);
CREATE INDEX idx_agent_apps_lifecycle ON agent_apps(lifecycle_state, cold_since);
-- rationale: MAU 体检 cron 任务按 lifecycle_state='active' 筛选，需索引加速

CREATE INDEX idx_agent_apps_degradation ON agent_apps(degradation_exempt) WHERE degradation_exempt = true;
-- rationale: 降级触发时需快速找出所有豁免 Agent，partial index 减少扫描量
```

### Session 表

```sql
CREATE INDEX idx_sessions_user ON sessions(user_id_hash, created_at DESC);
-- rationale: 用户历史会话列表按时间倒序

CREATE INDEX idx_sessions_agent ON sessions(agent_id, created_at DESC);
-- rationale: Agent 使用统计聚合

CREATE INDEX idx_sessions_status ON sessions(status, expires_at);
-- rationale: 会话清理 cron 任务扫描过期 session
```

### 审计日志表（分区表）

```sql
CREATE INDEX idx_audit_agent_time ON audit_logs(agent_id, timestamp);
-- rationale: 业务部门按 Agent 查审计日志（高频查询）

CREATE INDEX idx_audit_run_id ON audit_logs(run_id);
-- rationale: 按 RunSpec 追溯单条执行轨迹

CREATE INDEX idx_audit_user_hash ON audit_logs(user_id_hash, timestamp);
-- rationale: 合规审计按用户 hash 过滤
```

### 文件上传表

```sql
CREATE INDEX idx_file_uploads_session ON file_uploads(session_id);
-- rationale: 会话恢复时需列出该 session 的所有上传文件

CREATE INDEX idx_file_uploads_expires ON file_uploads(expires_at);
-- rationale: 过期文件清理 cron 任务
```

### 慢查询优化建议

| 查询场景 | 预期 SQL 模式 | 索引建议 |
|----------|-------------|---------|
| "某 Agent 过去 7 天的错误率" | `WHERE agent_id=? AND timestamp>?` | 复合索引 `(agent_id, timestamp, error_code)` |
| "某部门本月 token 消耗" | `WHERE scope='department' AND scope_id=? AND period_start=?` | 已覆盖：`(scope, scope_id, period_start)` |
| "某用户最近 10 条会话" | `WHERE user_id_hash=? ORDER BY created_at DESC LIMIT 10` | 已覆盖：`idx_sessions_user` |

---

## system_configs 典型键值**：

| key | value 示例 | 说明 |
|-----|-----------|------|
| `script_policy` | `{ "dependency_install": false, "network": false, ... }` | 全局脚本策略，见 [04-skill-package-spec.md](04-skill-package-spec.md) |
| `max_file_size_hard_limit` | `10485760` | 后端文件大小硬上限（字节），与 agent.yaml limits.max_file_size 联动 |
| `model_gateway_config` | `{ "models": { "qwen3-32b": { ... } } }` | 模型网关路由配置，见 [10-model-gateway.md](10-model-gateway.md) |
| `default_audit_retention_days` | `90` | 默认审计保留天数 |
| `mau_salt_version` | `"v1"` | 当前 MAU hash salt 版本号 |
| `degradation_auto_enabled` | `true` | 是否允许自动降级 |

---

## 数据库迁移策略

### 迁移工具

推荐使用 **Alembic**（SQLAlchemy 生态）或 **Flyway**（Java 生态，央企常用）。

| 工具 | 适用场景 | 推荐度 |
|------|---------|--------|
| **Alembic** | Python/FastAPI 项目，与 SQLAlchemy 集成 | ⭐⭐⭐ |
| **Flyway** | 央企已有 Java 技术栈，DBA 熟悉 | ⭐⭐⭐ |
| **Liquibase** | 需要 GUI 管理迁移历史 | ⭐⭐ |

### 迁移规范

1. **每个迁移一个文件**，命名格式：`YYYYMMDD_HHMMSS_description.py`
2. **迁移必须可回滚**（downgrade 函数必须实现）
3. **禁止在迁移中修改已有数据**（除非有明确的数据修复需求）
4. **敏感字段变更**（如删除列）需经过审批
5. **生产环境迁移**必须在维护窗口执行，由 DBA 操作

### 初始化流程

```bash
# 1. 创建迁移仓库
alembic init migrations

# 2. 生成初始 DDL
alembic revision --autogenerate -m "initial schema"

# 3. 执行迁移（首次部署）
alembic upgrade head

# 4. 验证
alembic current
```

---

## Agent 级 schemas/ 与 Skill 级 schemas/ 职责边界

```
Skill Package schemas/          Agent App schemas/
├── 定义输出格式的 JSON Schema   ├── 对 Skill schema 的覆盖/扩展（可选）
├── 由 Skill Creator 维护        ├── 由业务部门维护
└── 通过 RunSpec.output_schema   └── 当 Agent 需要自定义字段时生效
    绑定到 RunSpec                （如：合同审查助手需要额外字段"审批意见"）
```

**优先级规则**：

- Agent 级 `schemas/` 为空 → 使用 Skill 级 schema
- Agent 级 `schemas/` 存在同名 schema → **Agent 级覆盖 Skill 级**
- Agent 级 schema 必须兼容 Skill 级 schema 的核心字段（向后兼容校验）

**运行时加载顺序**（以 `output_schema: contract-review-report` 为例）：

1. Agent Runner 优先查找 `agents/<agent_id>/schemas/contract-review-report.json`
2. 若不存在，查找 `skills/<skill_id>/<version>/schemas/contract-review-report.json`
3. 两者都不存在 → schema 校验跳过（返回 `schema_valid: null`）
