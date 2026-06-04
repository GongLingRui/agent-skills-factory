# 03. Agent App 规范

> 版本：v0.6 · 2026-05-06

---

## Agent 目录结构

```
agents/
  contract-review-agent/
    agent.yaml          # 配置主文件（岗位说明书）
    skill/              # 唯一的 Skill 包（操作手册）
    schemas/            # 输出格式定义
    evals/              # 评测用例
```

---

## agent.yaml 完整规范

```yaml
# ========== 基础信息 ==========
id: contract-review-agent              # 唯一标识（小写字母、数字、连字符）
name: 合同审查助手                      # 显示名称
version: 0.1.0                         # 版本号（semver）
runspec_schema_version: 1              # RunSpec schema 版本（见 [05-runspec.md](05-runspec.md) §版本化）
description: 审查集团内部合同文本的风险，给修改建议
owner: legal-department                # 所属部门 / 负责人

# ========== 生命周期 ==========
lifecycle_state: active               # active / cold / archived

# ========== 标签 ==========
tags: [legal, contract, risk]          # 用于分类、检索和权限过滤

# ========== 发布策略 ==========
release:
  strategy: full                       # full / canary / pinned
  canary:
    percent: 10                        # 10% 流量用新版
    target_departments:                # 灰度目标部门（满足任一即灰度）
      - legal
    target_users:                      # 灰度目标用户白名单（可选，满足任一即灰度）
      - u_test001
  pinned_version: 0.0.9                # rollback 时用这个

# ========== 模型策略 ==========
model_policy:
  default: qwen3-32b
  fallback: qwen3-14b
  low_cost: qwen3-8b

# ========== Agent 专属指令 ==========
instruction: |
  你是合同审查助手，专门负责审查集团内部合同文本的风险点。
  审查范围包括：付款条款、违约责任、保密义务、知识产权、争议解决等。
  必须引用公司制度和标准模板作为依据，不确定时明确标注"需人工复核"。

# ========== Skill 绑定（P0 硬约束：只能挂一个） ==========
skill:
  id: clause-review
  version_pin: "~0.1.0"                # 可选，默认用最新兼容版

# ========== 工具白名单 ==========
tools:
  allow:
    - kb.search
    - doc.extract
    - risk.rule_check

# ========== 知识范围 ==========
knowledge_scopes:
  - group_legal_policy
  - contract_templates
  - historical_contract_cases

# ========== 输出 Schema ==========
output_schema: contract-review-report

# ========== 运行限制 ==========
limits:
  max_turns: 6                         # 最大对话轮数
  max_tokens: 8000                     # 单次输出最大 token
  timeout_seconds: 90                  # 单次请求超时
  max_file_size: 10MB                  # 单文件上传大小上限

# ========== 并发策略 ==========
concurrency:
  class: document                      # interactive / document / batch / privileged
  queue_priority: 5                    # 1-10，越大优先级越高

# ========== 降级豁免（仅 platform_admin 可修改） ==========
degradation_exempt: false              # true = 全局降级时不影响该 Agent（保留完整模型和工具）

# ========== 审计配置 ==========
audit:
  level: minimal                       # full / minimal（默认 minimal，不允许 off）
  trace_prompt: false                  # P0 不 trace prompt 内容（节省存储）
  trace_tool_calls: true               # 一定 trace（合规底线）
  trace_retrieval_ids: true            # 一定 trace（数据域审计）
  retain_days: 90                      # P0 默认 90 天

# ========== 企业治理扩展 ==========
enterprise:
  risk_tier: medium                    # low / medium / high
  compliance_checklist:                # 合规检查项
    - data_privacy
    - trade_secret
  mau_threshold: 5                     # 30 天 MAU 体检阈值，低于则转入 cold

# ========== UI 配置（不进 RunSpec，只影响前端渲染） ==========
ui_config:
  title: 合同审查助手
  avatar: /static/agents/contract.png
  welcome_message: |
    我可以帮你审查合同关键条款，识别风险并给出修改建议。
    请上传合同文件，或直接粘贴条款内容。
  input_placeholder: 上传合同或粘贴条款...
  quick_actions:
    - label: 审查全文
      prompt: "请审查整份合同的所有关键条款"
    - label: 重点条款
      prompt: "请重点审查付款、违约、保密三类条款"
  attachments:
    enabled: true
    accept: [.docx, .pdf, .txt]
    max_size_mb: 10
```

---

## 字段详解

### id

- 小写字母、数字、连字符
- 全局唯一，不可变更
- 用于 URL、API 路径、日志索引

### version

- 遵循 semver（主.次.补丁）
- Agent App 注册中心保留最近 10 个历史版本
- 升级后所有**新会话**用新版，**已运行会话**用旧版（RunSpec 钉死）

### runspec_schema_version

- 默认 1，未来演进时递增
- Runner 必须向后兼容 N=2 个大版本
- 保证审计日志里的旧 RunSpec 在升级后仍可复现

### lifecycle_state

| 状态 | 含义 | 用户可见 |
|------|------|---------|
| active | 正常运行 | 是，可访问 |
| cold | 低 MAU 被归档（也称 deprecated） | 否，从推荐位下架 |
| archived | 已废弃 | 否，完全不可访问 |

**状态转换**：

```
active ←──(MAU 体检不达标)──→ cold
  ↑                            │
  └──(重新评测通过)─────────────┘

active / cold ──(业务部门申请废弃)──→ archived

cold ──(cold 超过 90 天未重新激活)──→ archived   # 自动归档
```

**自动归档**：cron 任务每日检查，cold 状态超过 90 天且未重新激活的 Agent 自动转入 archived（详见 [21-cron-jobs.md](21-cron-jobs.md)）。

### release.strategy

| 策略 | 场景 | 行为 |
|------|------|------|
| full | ui_config 小改 | 新会话全部用新版 |
| canary | prompt / 工具 / schema 变更 | 按 percent / target_departments / target_users 放量 |
| pinned | 回滚 | 强制用 pinned_version |

**canary 的命中逻辑（满足任一即灰度）**：

```python
is_canary = (
    user_in_target_users(user_id, canary.target_users) or
    user_in_target_departments(department, canary.target_departments) or
    hash(user_id) % 100 < canary.percent
)
```

- 命中逻辑：满足**任一条件**即灰度（`or` 短路求值）
- 评估顺序：`target_users` → `target_departments` → `percent`（短路求值，先命中先返回）
- `target_users`：用于测试账号、业务 owner 提前验证
- `target_departments`：用于部门级灰度
- `percent`：按用户 ID hash 取模，保证同一用户始终命中同一版本

### tags

- 标签数组，用于 Agent 分类、检索和权限过滤
- 示例：`[legal, contract, risk]`
- 不影响运行逻辑，仅用于管理端展示和搜索

### enterprise

- `risk_tier`：风险等级（low / medium / high），影响审批流程和审计粒度
- `compliance_checklist`：合规检查项列表，Agent 上线前需逐项确认
- `mau_threshold`：30 天 MAU 体检阈值，低于则转入 cold（默认 5）
- `risk_tier_prompt_override`：（可选）Agent 级 risk_tier 映射指令覆盖。只能**追加**约束，不能删除 high 等级的强制复核条款。详见 [07-skill-compiler.md](07-skill-compiler.md) §risk_tier 映射规则

### model_policy

- default：首选模型
- fallback：default 不可用时降级（容量不足 / 超时 / 错误率过高）
- low_cost：高峰期降级用（§9.3 第 3 步）

### instruction

- Agent 级专属系统指令，由业务部门编写
- 在 Prompt 拼装优先级中位于 `org_policy` 之后、`risk_tier` 映射指令之前
- 用于描述该 Agent 的专属角色定位、业务范围、输出风格
- 若为空则跳过，不影响 Skill 级指令生效

### skill（P0 硬约束）

- **只能挂一个** Skill Package
- `id`：Skill 标识
- `version_pin`：可选，支持 semver range（如 `~0.1.0`、`^1.0.0`）
- 不填 `version_pin` → 用 Skill Registry 最新兼容版

### tools.allow

- 白名单模式，**不在列表中的工具一律不可调用**
- 最终可用 = Agent 声明 ∩ Skill 需要 ∩ 用户权限 ∩ 部门权限 ∩ Tool Gateway 策略

### knowledge_scopes

- 声明该 Agent 可能需要查哪些知识域
- 最终可用 = Agent 声明 ∩ Skill 建议 ∩ 用户可访问数据域

### concurrency.class

| 等级 | 延迟要求 | 典型场景 |
|------|---------|---------|
| interactive | 低延迟（<3s） | 制度问答、闲聊 |
| document | 中等延迟（<30s） | 合同审查、会议纪要 |
| batch | 可排队（<5min） | 批量材料处理 |
| privileged | 最高优先级 | 领导审批、紧急业务 |

### audit.level

| 档位 | trace 内容 | 存储成本 |
|------|-----------|---------|
| minimal（默认） | user_id_hash / agent_id / run_id / tool_calls / token / cost / error / retrieval_ids | ~5KB/会话 |
| standard | minimal + prompt 摘要 + retrieval 命中 ID | ~20KB/会话 |
| full | standard + 完整 prompt + 完整 output | ~100KB+/会话 |

**关键约束**：不允许设为 off，schema 校验阶段拒绝。

---

## Retention Gate 机制（Agent 生命周期质检）

### 设计意图

Retention gate 是 Agent App Factory 的**出厂质检 + 召回机制**，解决两个 KPI 之间的张力：

- **数量拉力** → 工厂模式让 Agent 数量快速增长
- **MAU 拉力** → 必须保证推荐位上的 Agent 有人用、用得好

没有 retention gate，低质量 Agent 会稀释平台价值，用户找不到好用的 Agent，MAU 被拖垮。

### 机制概览

```
Agent 上线（active）
  ↓
每日 MAU 体检（30 天滚动窗口）
  ├─ 达标（≥ mau_threshold）→ 保持 active
  └─ 不达标（< mau_threshold）→ 转入 cold
       ↓
   从推荐位下架，但不被删除
   业务部门收到通知，可申请重新激活（需重新评测）
       ↓
   cold 超过 90 天仍未激活 → 自动 archived（完全不可访问）
```

### 状态转换规则

| 转换 | 触发条件 | 动作 |
|------|---------|------|
| active → cold | 连续 30 天 MAU < `enterprise.mau_threshold` | 从推荐位下架，通知业务部门 |
| cold → active | 业务部门申请重新激活 + 重新评测通过 | 恢复推荐位 |
| active / cold → archived | 业务部门主动申请废弃 或 cold 超 90 天 | 完全不可访问 |

### 核心价值

1. **数量 KPI 不被噪音稀释** —— cold registry 里的 Agent 不计入"活跃 Agent 数"
2. **MAU KPI 不被低质量 Agent 拖垮** —— 默认推荐位永远是高 MAU 的
3. **业务部门有反馈循环** —— 被冷藏会促使业务部门改 Skill / 改 prompt / 改输出格式

### 实施要点

- `mau_threshold` 默认 5（30 天内至少 5 个不同用户使用），业务部门可在 `agent.yaml` 中自定义
- 体检由每日 cron 执行，详见 [21-cron-jobs.md](21-cron-jobs.md) §MAU 体检与自动归档
- MAU 计算基于最小服务器元数据（哈希化 + 日粒度），详见 [12-security-audit.md](12-security-audit.md) §MAU 计算

### ui_config

**明确不进 RunSpec**——改 ui_config 只刷新 widget，不影响后端任何运行逻辑。业务部门可以快速迭代欢迎语、快捷指令，不需要重新编译 RunSpec。

### limits

| 字段 | 说明 | 默认值 |
|------|------|--------|
| max_turns | 最大**模型调用次数**（turn = 一次模型推理，不是用户消息轮数；ReAct 循环中 tool result 后再次调模型也算一次 turn） | 6 |
| max_tokens | 单次输出最大 token | 8000 |
| timeout_seconds | 单次请求超时（秒） | 90 |
| max_file_size | 单文件上传大小上限（字节） | 10485760（10MB） |
| context_memory | 可选。长上下文与会话记忆：默认模型摘要（非破坏性 snip）、工具结果摘要、跨会话 ``user_agent_memory``；写入 RunSpec ``runtime``；字段见 [08-agent-runner.md](08-agent-runner.md) §上下文治理 **Runner 实现（P0）** | （缺省则用 Runner 内置默认） |

**`limits.max_file_size` 与 `ui_config.attachments.max_size_mb` 的关系**：

- `limits.max_file_size`：后端硬限制（字节），API `/upload` 和 Doc Worker 统一校验，**防绕过**
- `ui_config.attachments.max_size_mb`：前端预检（MB），widget 上传前即时提示用户，**改善体验**
- 两者必须保持一致：`ui_config.attachments.max_size_mb * 1024 * 1024 <= limits.max_file_size`
- 若前端配置大于后端，以后端为准（后端二次校验拒绝超限文件）
- 建议：管理后台修改 `limits.max_file_size` 时，同步更新 `ui_config.attachments.max_size_mb`

**一致性校验机制**：Agent App 注册中心在保存 agent.yaml 时，必须强制执行：

```python
assert ui_config.attachments.max_size_mb * 1024 * 1024 <= limits.max_file_size, (
    "前端 max_size_mb 不得大于后端 max_file_size"
)
```

不满足则拒绝保存，返回 `INVALID_PARAMS` 错误。

### output_schema

- 声明该 Agent 输出的结构化格式名称
- 对应 **Agent 级** `schemas/` 目录下的 JSON Schema 文件名（不含扩展名），若不存在则 fallback 到 **Skill 级** `schemas/`
- 例：`contract-review-report` 对应以下查找顺序：
  1. `agents/contract-review-agent/schemas/contract-review-report.json`（Agent 级，优先）
  2. `skills/clause-review/v0.1.0/schemas/contract-review-report.json`（Skill 级，fallback）
- Agent 级 schema 可覆盖/扩展 Skill 级 schema，用于业务部门自定义字段
- Runner 在模型输出最终答案后按此 schema 做校验

---

## Skill 来源边界（重要）

Skill 包由**独立的 Skill Creator 系统**产出。本系统只消费符合规范的 Skill 目录，不负责：

- Skill 创建 UX
- 业务用户表单
- Skill 调试器

Skill Creator 是上游项目，本系统通过 Skill Registry 接口拉取或挂载。

---

## 业务部门新增 Agent 的步骤

1. 复制一个现有 Agent 目录作为模板
2. 修改 `agent.yaml`：id / name / owner / model_policy / skill / tools / knowledge_scopes
3. 替换 Skill 包（或沿用现有）
4. 调整 `ui_config`：标题 / 欢迎语 / 快捷指令 / 文件上传配置
5. 提交到 Agent App 注册中心（走审批流程）

**不需要碰运行时代码**。
