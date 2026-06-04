# 07. Skill Compiler 设计

> 版本：v0.6 · 2026-05-06

---

## 一句话职责

把 Agent + Skill + 权限 + 工具策略**编译**成 RunSpec。

**类比**：装配车间——把零件（agent.yaml）+ 操作手册（Skill）+ 安全规范（policy）组装成一份"出厂订单"（RunSpec）。

---

## 编译流程

```
输入：agent_id + user_id + department + portal-JWT claims
  ↓
1. 加载 agent.yaml（按版本/灰度策略）
  ↓
2. 加载 Skill Package（按 skill.version_pin）
  ├─→ SKILL.md
  ├─→ enterprise.yaml
  ├─→ references/（按 load_policy 分类）
  └─→ schemas/
  ↓
3. 加载策略叠加
  ├─→ platform_policy（系统级铁律）
  ├─→ org_policy（部门级策略）
  └─→ agent.yaml 自身配置
  ↓
4. 权限交集计算
  ├─→ 工具白名单 = agent.tools ∩ skill.tools ∩ user.permissions ∩ department.permissions ∩ tool_gateway.policy
  ├─→ 知识范围 = agent.knowledge_scopes ∩ skill.knowledge_scopes ∩ user.data_domains
  └─→ 脚本钩子：P0 固定输出 `{}`（忽略 Skill 内运行时脚本声明）；P2+ 再按 skill.script_hooks ∩ user.script_permissions 生成
  ↓
5. Prompt 拼装（按优先级）
  platform_policy > org_policy > agent_instruction > risk_tier 映射指令 > enterprise.yaml > SKILL.md 主体 > always_references > 用户输入
  ↓
6. 生成 RunSpec
  ├─→ 填入所有字段
  ├─→ 算 skill_package_hash
  ├─→ 分配 run_id
  └─→ 打上 runspec_schema_version
  ↓
输出：RunSpec（不可变）
```

---

## 输入

| 字段 | 来源 |
|------|------|
| agent_id | URL 参数 |
| user_id | portal-JWT |
| department | portal-JWT |
| permissions | portal-JWT（或 RBAC 系统实时查） |
| data_domains | RBAC 系统实时查 |
| portal-JWT claims | 认证信息 |

---

## 各阶段详解

### 阶段 1：加载 agent.yaml

- 从 Agent App 注册中心读取
- 按 `release.strategy` 决定版本：
  - full → 最新版
  - canary → 按 percent / target_departments 决定
  - pinned → pinned_version
- 检查 `lifecycle_state` 必须为 active

### 阶段 2：加载 Skill Package

- 从 Skill Registry 读取
- 按 `skill.version_pin` 解析 semver range
- 加载 SKILL.md、enterprise.yaml、references/、schemas/
- 不加载 scripts/（只记录 hooks）

### 阶段 3：策略叠加

**platform_policy**（系统级，最高优先级）和 **org_policy**（部门级）的存储与管理：

- **存储**：存于数据库 `platform_policies` / `org_policies` 表（详见 [17-data-models.md](17-data-models.md)）
- **维护权限**：platform_policy 仅 `platform_admin` 可写；org_policy 由对应 `department_admin` 维护
- **版本化**：每次修改自动递增 version，旧版本保留用于审计复现
- **生效机制**：
  - 策略变更**不触发已运行 RunSpec 失效**（RunSpec 的 prompt 层在编译时已钉死）
  - 新会话编译时才拉取最新策略版本
  - 策略缓存 TTL：1 分钟（Redis），变更后最长 1 分钟生效
  - **多实例缓存同步**：实例 A 修改 policy 后，写数据库 → 写 Redis → 发布 Pub/Sub `policy:updated`；其他实例订阅该 channel，收到后清除本地 Caffeine/LRU 缓存，确保集群一致性

**platform_policy 示例**（系统管理员维护，全平台统一）：

```yaml
platform_policy:
  prompt: |
    你是央企内部智能助手。你的回答必须：
    1. 不涉及国家秘密、商业秘密
    2. 不给出法律意见替代专业律师
    3. 不泄露其他用户信息
    4. 不确定时明确标注"需人工复核"
```

**org_policy 示例**（各部门可自定义）：

```yaml
org_policy:
  department: legal
  prompt: |
    你是法务部智能助手。引用制度时必须标注文号和生效日期。
```

**enterprise.yaml 在策略叠加中的角色**：

- `enterprise.yaml` 中 **非执行类** 的治理声明（如 `risk_tier` 对应的策略提示、合规检查项的 prompt 片段）在此阶段拼入 prompt
- `enterprise.yaml` 中 **执行类** 字段（`tools.require/optional`、`knowledge_scopes.suggest`、`output_schema`、`limits`、`scripts` 等）直接映射到 RunSpec 对应字段，不经过 prompt 层
- 执行类字段的优先级：若与 `agent.yaml` 冲突，以 `agent.yaml` 为准（业务部门配置优先于 Skill 包默认配置）

### 阶段 4：权限交集

**工具白名单计算**：

```python
allowed_tools = (
    set(agent.tools.allow) &
    set(skill.tools.require + skill.tools.optional) &
    set(user.permissions) &
    set(department.permissions) &
    set(tool_gateway.available_tools)
)
```

**知识范围计算**：

```python
retrieval_scopes = (
    set(agent.knowledge_scopes) &
    set(skill.knowledge_scopes.suggest) &
    set(user.data_domains)
)
```

### 阶段 5：Prompt 拼装

按优先级顺序拼接成 `prompt_parts` 列表：

```
1. platform_policy（系统铁律）
2. org_policy（部门策略）
3. agent.yaml 中的 agent_instruction（如有）
4. risk_tier 映射指令（按 enterprise.yaml / agent.yaml 覆盖后的结果注入）
5. enterprise.yaml 中的其他策略性提示（如合规约束声明）
6. SKILL.md 主体（去掉 frontmatter）
7. always references（内容直接拼入）
8. on_demand references（只列目录，不拼内容）
9. indexed references（只列 scope，不拼内容）
```

#### risk_tier 映射规则

Skill Compiler 读取 `enterprise.yaml` 中的 `risk_tier` 字段，按以下顺序确定最终注入的治理指令：

1. **Agent 级覆盖**：检查 `agent.yaml` 是否有 `enterprise.risk_tier_prompt_override`
   - 若有 → 使用 Agent 级映射（必须兼容 Skill 级核心字段）
2. **Skill 级配置**：检查 `enterprise.yaml` 是否有 `risk_tier_prompt_map`
   - 若有 → 使用该 Skill 自定义的映射
3. **系统默认**：以上皆无 → 使用 Compiler 内置默认映射表

**默认映射表（内置）**：

| risk_tier | 注入 prompt 内容 |
|-----------|-----------------|
| `low` | `【风险等级：低】请按常规流程处理，无需额外审批标注。` |
| `medium` | `【风险等级：中】输出涉及业务判断时，必须标注"需人工复核"。引用制度时必须标注文号和生效日期。` |
| `high` | `【风险等级：高】所有输出必须标注"需人工复核"，不得替代专业判断。涉及金额、期限、权利义务的结论必须列出依据来源。不确定时必须明确拒绝回答，禁止编造依据。` |

**约束**：
- `high` 等级的"必须标注需人工复核"和"禁止编造依据"为**不可覆盖的强制条款**
- Agent 级覆盖只能**追加**约束，不能**删减** Skill 级或系统默认的强制条款

### 阶段 6：生成 RunSpec

- 生成唯一 `run_id`：格式 `run_YYYYMMDD_HHMMSS_{nanoid(6)}`，其中 nanoid 为 6 位随机字母数字（如 `run_20260507_143052_a1b2c3`），避免高并发下序号冲突
- 计算 `skill_package_hash`：整个 Skill 包（不含 evals/）的 sha256
- 填入 runtime 字段（model / fallback / limits）
- 填入 audit 字段
- 打上 `runspec_schema_version`

---

## 错误处理

| 错误场景 | 响应 |
|---------|------|
| agent.yaml 不存在 | 404 Agent not found |
| agent.yaml lifecycle_state != active | 403 Agent inactive |
| 用户无权限访问该 Agent | 403 Forbidden |
| Skill Package 不存在 | 500 Skill not found（内部错误，不应发生） |
| Skill Package schema 校验失败 | 500 Skill invalid |
| 权限交集为空（无可用工具） | 400 No tools available for this user |
| runspec_schema_version 不支持 | 500 Unsupported RunSpec version |

---

## 性能考虑

- agent.yaml 和 Skill Package 应常驻内存缓存（Redis / 本地缓存）
- 权限交集涉及 RBAC 查询，可缓存用户权限（TTL 5 分钟）
- 编译本身是无状态纯函数，可水平扩展
- 编译耗时应 < 100ms（P0 目标）

---

## Prompt 拼装模板语法规范

Compiler 使用 **Jinja2** 作为模板引擎，所有 prompt 片段通过模板渲染后写入 `RunSpec.prompt_parts`。

### 模板变量上下文

```python
{
  "platform_policy": str,       # 系统级策略文本
  "org_policy": str | None,     # 部门级策略文本
  "agent_instruction": str,     # agent.yaml 中的 instruction
  "risk_tier_prompt": str,      # 按 risk_tier 映射的治理指令
  "enterprise_prompts": list,   # enterprise.yaml 中的其他策略性提示
  "skill_body": str,            # SKILL.md 去掉 frontmatter 后的正文
  "always_refs": list[dict],    # [{"name": ..., "content": ...}]
  "lazy_refs": list[dict],      # [{"name": ..., "path": ...}]
  "indexed_refs": list[dict],   # [{"name": ..., "scope": ...}]
}
```

### 分隔符规范

为避免 prompt 段间相互干扰，各段之间插入**不可见的 XML 分隔标签**（模型能识别但不会被用户看到）：

```
<system>
  <platform_policy>
    {{ platform_policy }}
  </platform_policy>
  <org_policy>
    {{ org_policy }}
  </org_policy>
  ...
</system>
```

**约束**：
- 所有变量默认**HTML 转义**（`{{ var }}` 自动转义 `< > &`），防止 Skill Creator 的 prompt 意外破坏 XML 结构
- 如需原样输出（如代码示例），使用 `{{ var | safe }}`
- 空变量（`None` 或 `""`）对应的 XML 标签**不渲染**，避免空白段干扰模型

### 与 references/ 的集成

`always_references` 的内容在模板中按文件顺序拼接：

```jinja2
{% for ref in always_refs %}
<reference name="{{ ref.name }}">
{{ ref.content }}
</reference>
{% endfor %}
```

**长度限制**：单个 `always_refs` 内容超过 `limits.max_reference_tokens`（默认 4000 tokens）时，Compiler 报错 `REFERENCE_TOO_LONG`，拒绝编译——防止长 reference 挤占模型上下文窗口。

### 编译后校验

模板渲染完成后，Compiler 执行以下校验：
1. **XML 结构完整性**：检查所有 `<system>`、`<platform_policy>` 等标签是否成对闭合
2. **空 prompt 检测**：若 `prompt_parts` 渲染后总长度 < 100 字符，报错 `PROMPT_TOO_SHORT`
3. **敏感词过滤**：扫描是否包含 `user_id`、真实姓名、手机号等敏感信息（误配置时告警）

---
