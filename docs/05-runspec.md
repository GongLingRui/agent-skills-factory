# 05. RunSpec 详解

> 版本：v0.6 · 2026-05-06

---

## 通俗解释

**RunSpec = 这次请求的"出厂订单"。**

**类比一 · 淘宝订单**：你购物车加加减减是配置（agent.yaml + Skill），点提交那一刻系统生成订单（RunSpec），订单一旦生成不能改，仓库（Runner）按订单发货。哪怕你购物车后来变了，这次发货还是按订单走。

**类比二 · 编译产物**：源代码（agent.yaml + SKILL.md + policy）经过编译器（Skill Compiler）生成机器码（RunSpec），CPU（Runner）执行机器码。改源代码不影响正在执行的机器码。

---

## P0 裁剪 vs 完整 RunSpec

实现 **必须** 遵守 [34-p0-delivery-spec.md](34-p0-delivery-spec.md)。与本页 YAML 示例的关系：

| 维度 | P0（MVP） | P2+（完整能力） |
|------|-----------|----------------|
| `script_hooks` | **固定 `{}`**；Compiler **忽略** Skill 包内运行时 `scripts` 声明（不报错） | 可有 `preprocess` 等，由受控 Worker 按白名单执行 |
| `audit.level` | **minimal**（默认，**不允许 off**） | 可为 standard / full |

- **P0 开发**：以下「P0 典型形状」为默认编译结果；勿实现非空的 `script_hooks`。
- **对照完整能力**：需要阅读「完整形态示例」与本文后半「实际加载流程」中带脚本的步骤（标注 **P2+**）。

---

## RunSpec Schema（v1）

### P0 典型形状（`script_hooks` 为空）

```yaml
runspec_schema_version: 1
run_id: run_20260506_143052_a1b2c3
agent_id: contract-review-agent
agent_version: 0.1.0
skill_id: clause-review
skill_version: 0.1.0
skill_package_hash: abc123...
skill_file_manifest:
  references/checklist.md: def456...
  references/risk-levels.md: ghi789...
  schemas/contract-review-report.json: jkl012...
user_id: u123
department: legal

prompt_parts:
  - role: platform_policy
    content: "..."
  - role: org_policy
    content: "..."
  - role: agent_instruction
    content: "..."
  - role: skill_instruction
    content: "..."
  - role: always_reference
    content: "..."

lazy_references:
  - name: checklist
    path: references/checklist.md

indexed_references:
  - name: legal-policy
    scope: group_legal_policy

allowed_tools:
  - kb.search
  - doc.extract

retrieval_scopes:
  - group_legal_policy
  - contract_templates

script_hooks: {}                     # P0 固定空对象；勿填 preprocess

output_schema: contract-review-report

runtime:
  model: qwen3-32b
  fallback_model: qwen3-14b
  max_turns: 6                       # 模型调用次数上限（非「用户发几条消息」）
  timeout_seconds: 90
  max_tokens: 8000

audit:
  level: minimal                     # P0 默认 minimal，不允许 off
```

### 完整形态示例（P2+，`script_hooks` 可非空）

下列片段展示 **未来阶段** RunSpec 在脚本钩子上的扩展形态；P0 **不得**生成非空 `script_hooks`。

```yaml
runspec_schema_version: 1
run_id: run_20260506_143052_a1b2c3  # 这次跑的唯一 ID（格式 run_YYYYMMDD_HHMMSS_nanoid(6)）
agent_id: contract-review-agent
agent_version: 0.1.0                 # 钉死版本
skill_id: clause-review
skill_version: 0.1.0
skill_package_hash: abc123...        # 整个 Skill 包 sha256（锚定 hash）
skill_file_manifest:                 # 包内每个文件的 sha256（运行时单文件校验）
  references/checklist.md: def456...
  references/risk-levels.md: ghi789...
  schemas/contract-review-report.json: jkl012...
user_id: u123
department: legal

prompt_parts:                        # 已拼好的 prompt，按优先级
  - role: platform_policy            # 平台铁律（最高）
    content: "..."
  - role: org_policy                 # 部门策略
    content: "..."
  - role: agent_instruction
    content: "..."
  - role: skill_instruction
    content: "..."
  - role: always_reference
    content: "..."

lazy_references:                     # on_demand 引用目录（不含内容）
  - name: checklist
    path: references/checklist.md
  - name: risk-levels
    path: references/risk-levels.md

indexed_references:                  # 进检索索引的引用
  - name: legal-policy
    scope: group_legal_policy

allowed_tools:                       # 已做完权限交集
  - kb.search
  - doc.extract
  - risk.rule_check

retrieval_scopes:                    # 已按用户权限过滤
  - group_legal_policy
  - contract_templates

script_hooks:                        # P2+：受控 Worker 白名单
  preprocess:
    - normalize_contract_text

output_schema: contract-review-report

runtime:
  model: qwen3-32b
  fallback_model: qwen3-14b
  max_turns: 6                          # 最大模型调用次数（turn = model call，不是用户-助手对话轮数）
  timeout_seconds: 90
  max_tokens: 8000

audit:
  level: minimal
```

---

## 它的灵魂是"不变"

RunSpec 一旦编译出来**就不能改**。这个不变性带来三件事：

1. **审计可复现**：留 RunSpec + 执行轨迹，事后能完整复现这次跑了什么
2. **权限收敛**：所有权限交集在 Skill Compiler 一次性算完，Runner 只看字段，不再回头查
3. **升级安全**：长任务跑 60 秒中间 agent.yaml 升级了，本次仍按编译时的 RunSpec 走，不会半新半旧

**RunSpec 不是中间数据结构，是执行不变量。** 它的存在让 Agent Runner 成为纯执行器，所有判断收敛到 Skill Compiler 一处。

---

## 优先级和交集规则

### 合并 prompt 的优先级（高的覆盖低的）

> platform_policy > org_policy > agent_instruction > risk_tier 映射指令 > enterprise.yaml 其他策略性提示 > SKILL.md 主体 > always_references > on_demand references > indexed references > 用户输入

**与 Skill Compiler 阶段对齐**：详见 [07-skill-compiler.md](07-skill-compiler.md) §Prompt 拼装。

### 权限交集（实际可用 = 五个集合的交集）

> 实际可用工具 = Agent 声明 ∩ Skill 需要 ∩ 用户权限 ∩ 部门权限 ∩ Tool Gateway 策略
>
> 实际知识范围 = Agent 声明 ∩ Skill 建议 ∩ 用户可访问数据域

---

## 多轮对话与 RunSpec（重要澄清）

**通俗讲**：**一次"会话"对应一份 RunSpec，多轮对话都在这份 RunSpec 下展开。**

> **错误理解**：每条用户消息 = 一次新 RunSpec
> **正确理解**：用户打开 Agent → 编译一份 RunSpec → 整个会话都按这份订单跑

**为什么这样**：

- RunSpec 是"出厂订单"，一次会话从开始到结束按同一份订单走，不能中途换订单
- 多轮上下文（历史消息）作为"订单的执行记录"，不是订单本身
- agent.yaml / Skill 在会话中途升级了？**本次会话仍用编译时的 RunSpec，下次新会话才用新版**

### 会话边界（什么时候触发新 RunSpec）

| 场景 | 是否新 RunSpec |
|------|---------------|
| 用户打开 Agent | **是** |
| 用户切换 Agent（顶栏切换，见 [11-chat-widget.md](11-chat-widget.md)） | **是** |
| 用户关 tab 再打开 | **是** |
| 用户对话中点"开新会话" | **是** |
| 用户连续追问多轮 | **否**（同一份 RunSpec） |
| max_turns 触发自动结束 | **是**（提示用户开新会话） |
| 单次会话 token 超模型上限 | **是**（提示用户开新会话） |

### 多轮上下文的处理

- 历史消息作为 prompt 的一部分追加（不进 RunSpec 的 prompt_parts，而是作为运行时上下文）
- max_turns 限制 **模型调用次数**（与 `runtime.max_turns` 语义一致，不是「用户消息条数」）
- 接近 token 上限时 widget 提示"对话即将达到上限，建议开新会话"，不暴力截断

### RunSpec 不变 ≠ 权限永远不变

RunSpec"不变"指的是 **prompt 拼装层**（agent_instruction / skill_instruction / always references）会话期间不变——保证版本一致和可复现。但 **权限 / 限流 / 模型降级 / 工具下线** 由 Tool Gateway 和模型网关**每次调用时实时校验**，以 RunSpec 上界 ∩ 当前最新策略为准——**以更小的能力为准**。

也就是说：用户部门变更、工具紧急下线、风控封禁、模型降级这些状态变化，会在下一次工具调用 / 模型路由时立刻反映；不需要中途重编译 RunSpec。

---

## RunSpec schema 版本化

agent.yaml 顶部加 `runspec_schema_version: 1`，未来 RunSpec 字段演进时：

- v1 RunSpec 由 Runner v1 执行
- v2 引入新字段（如 multi-step DAG）由 Runner v2 执行
- Runner 必须支持读取自己之前的 schema 版本（**向后兼容窗口 N=2 个大版本**）

**为什么**：审计日志里的旧 RunSpec 必须能在升级后的系统里复现。没有 schema_version，未来的代码看不懂过去的 RunSpec，"可复现"承诺破产。

---

## RunSpec 装什么 / Skill 包剩下的东西怎么办

**核心规则**：RunSpec **不装整个 Skill 包**，只装"主体 + 引用路径 + 版本 hash"。reference / scripts 是**运行时按需拉**的。

**类比 · 流水线工序卡**：流水线工人手里只有"工序卡"（RunSpec）——卡上写明工序步骤、用的工具清单、零件料号、配方文件号。**真正的零件 / 配方 / 模具不打印在卡上**，工人按料号去仓库领。

### 编译时进 RunSpec（一次性塞进去）

| 内容 | 为什么编译时进 |
|------|---------------|
| Skill 元数据（id / version / hash） | RunSpec 必须钉死版本，审计可复现 |
| SKILL.md 主体指令 | 这是模型的"系统 prompt"，必须每次都看到 |
| enterprise.yaml 的执行字段（allowed_tools / output_schema / limits） | RunSpec 的核心字段直接来自这里 |
| load_policy: always 的 references | 标了"必读"的短规则，直接拼进 prompt |
| 其他 references 的"目录"（路径 + 加载策略，**不含内容**） | 让模型知道"我有哪些资料可拉" |
| skill_package_hash（整个 Skill 包的 sha256） | 包级锚定 hash，快速发现包级篡改 / 半路升级 |
| skill_file_manifest（包内各文件的 sha256 映射表） | 运行时按需拉单文件时做精确 hash 校验 |

### 不进 RunSpec（运行时按需拉）

| 内容 | 什么时候拉 |
|------|-----------|
| load_policy: on_demand 的 references | 模型在循环中调用 read_reference(name=X) 工具时 |
| load_policy: indexed 的 references | 进检索索引，由 kb.search 查 |
| scripts/*.py | 受控 worker 实际调用脚本那一刻拉取 |
| schemas/*.json | 模型输出校验时按路径读 |
| examples.md 大段内容 | 按 always / on_demand 分类处理 |

**关于 schemas/*.json 的运行时加载路径**（详见 [08-agent-runner.md](08-agent-runner.md) §Schema 校验）：

Agent Runner 校验输出时按以下顺序查找 JSON Schema：

1. `agents/{agent_id}/schemas/{output_schema}.json`（Agent 级，业务部门自定义）
2. `skills/{skill_id}/{skill_version}/schemas/{output_schema}.json`（Skill 级，默认）

- Agent 级 schema **覆盖** Skill 级 schema（同名时）
- Agent 级 schema 必须兼容 Skill 级 schema 的核心字段（向后兼容校验）
- 两者都不存在 → schema 校验跳过，返回 `schema_valid: null`

**核心判据**：**只有"每次都用得到"的内容才进 RunSpec**。其他都是按需。

---

## 实际加载流程（合同审查 Skill 举例）

> 1. 用户打开 contract-review-agent
>
> 2. **Skill Compiler 编译 RunSpec**：
>    - 读 SKILL.md → 主体指令进 prompt_parts
>    - 读 enterprise.yaml → allowed_tools 等进 RunSpec；**P0** 忽略 `scripts` 声明且 `script_hooks` 输出 `{}`
>    - 读 references/risk-levels.md（标 always）→ 内容直接拼进 prompt_parts（短规则必看）
>    - 读 references/checklist.md（标 on_demand）→ 只把路径写进 RunSpec.lazy_references = ['checklist']
>    - 算整个 Skill 包的 sha256 → RunSpec.skill_package_hash = 'abc123...'
>    - 算每个文件的 sha256 → RunSpec.skill_file_manifest = {'references/checklist.md': 'def456...', ...}
>
> 3. **Agent Runner 启动工具调用循环**：
>    - 模型看到 prompt（含主体 + always references）
>    - 模型说："我要按合同类型查清单"
>    - 模型调用 read_reference(name='checklist')
>    - Tool Gateway 校验：checklist 在 RunSpec.lazy_references 白名单 ✓
>    - 从 Skill Registry 拉 contract-review v0.1.0 的 checklist.md
>    - 校验文件 hash 跟 RunSpec.skill_file_manifest['references/checklist.md'] 一致 ✓
>    - 内容回传给模型作为新一轮 prompt 输入
>
> 4. **（P2+）模型触发预处理脚本 `normalize_contract_text`**：
>    - 受控 worker 从 Skill Registry 拉该版本的脚本
>    - 校验 hash ✓
>    - 沙箱执行 → 结果回模型
>    - **P0 不执行此路径**：无受控脚本 Worker，`script_hooks` 恒为空

---

## 版本一致性保证

RunSpec 用**两级 hash**保证版本一致性：

| hash 级别 | 字段 | 用途 |
|-----------|------|------|
| 包级锚定 | `skill_package_hash` | 快速比对整个 Skill 包是否被篡改或半路升级；Registry 返回包级 hash 时先做粗校验 |
| 文件级精确 | `skill_file_manifest` | 运行时按需拉单个文件（reference / script / schema）时，按路径取对应文件的 sha256 做精确校验 |

**运行时校验流程**：

> 拉 references/checklist.md
> ↓
> 计算文件当前 sha256
> ↓
> 跟 RunSpec.skill_file_manifest['references/checklist.md'] 比对
> ↓
> 匹配 ✓ → 用
> 不匹配 ✗ → 报错 "Skill 包版本不一致"，会话异常终止

**`skill_package_hash` 计算范围**：

包级 hash 覆盖 Skill Package 中所有影响运行行为的文件：

- `SKILL.md`（含 frontmatter 和主体）
- `enterprise.yaml`
- `references/` 目录下所有文件（含 always / on_demand / indexed）
- `schemas/` 目录下所有 JSON Schema
- `templates/` 目录下所有模板文件
- `scripts/` 目录下所有脚本文件

**不纳入 hash 的文件**：

- `evals/` 目录（评测集不影响运行时行为）
- `.git/`、`.DS_Store` 等隐藏文件
- `README.md` 等纯说明文档（若存在）

**计算方式**：按文件路径字典序排序后，逐个计算 sha256，最后对整个有序列表再算一次 sha256（即内容寻址清单哈希，manifest hash）。

**包级 hash 的额外作用**：Skill Registry 返回包级 hash 若与 `skill_package_hash` 不一致，说明 Registry 上的该版本包已被整体替换（非正常升级），立即拒绝加载并告警。

**Skill Registry 保留所有历史版本**（不物理删除，只标 deprecated）。即使 Skill Creator 升级到 v0.2.0，已经在跑的 v0.1.0 会话仍能从 Registry 拉到当时的文件。

---

## RunSpec 正式 JSON Schema（v1）

用于校验 RunSpec 结构合法性和审计复现：

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "RunSpec_v1",
  "type": "object",
  "required": [
    "runspec_schema_version", "run_id", "agent_id", "agent_version",
    "skill_id", "skill_version", "skill_package_hash", "user_id",
    "department", "prompt_parts", "allowed_tools", "runtime", "audit"
  ],
  "properties": {
    "runspec_schema_version": { "type": "integer", "enum": [1] },
    "run_id": { "type": "string", "pattern": "^run_[0-9]{8}_[0-9]{6}_[a-z0-9]{6}$" },
    "agent_id": { "type": "string", "maxLength": 128 },
    "agent_version": { "type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$" },
    "skill_id": { "type": "string", "maxLength": 128 },
    "skill_version": { "type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$" },
    "skill_package_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "skill_file_manifest": {
      "type": "object",
      "additionalProperties": { "type": "string", "pattern": "^[a-f0-9]{64}$" }
    },
    "user_id": { "type": "string", "maxLength": 128 },
    "department": { "type": "string", "maxLength": 64 },
    "prompt_parts": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["role", "content"],
        "properties": {
          "role": {
            "type": "string",
            "enum": ["platform_policy", "org_policy", "agent_instruction", "skill_instruction", "always_reference"]
          },
          "content": { "type": "string", "maxLength": 500000 }
        }
      }
    },
    "lazy_references": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "path"],
        "properties": {
          "name": { "type": "string" },
          "path": { "type": "string" }
        }
      }
    },
    "indexed_references": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "scope"],
        "properties": {
          "name": { "type": "string" },
          "scope": { "type": "string" }
        }
      }
    },
    "allowed_tools": {
      "type": "array",
      "items": { "type": "string", "maxLength": 128 }
    },
    "retrieval_scopes": {
      "type": "array",
      "items": { "type": "string", "maxLength": 128 }
    },
    "script_hooks": {
      "type": "object",
      "properties": {
        "preprocess": { "type": "array", "items": { "type": "string" } }
      }
    },
    "output_schema": { "type": "string", "maxLength": 128 },
    "runtime": {
      "type": "object",
      "required": ["model", "max_turns", "timeout_seconds", "max_tokens"],
      "properties": {
        "model": { "type": "string" },
        "fallback_model": { "type": "string" },
        "max_turns": { "type": "integer", "minimum": 1, "maximum": 20 },
        "timeout_seconds": { "type": "integer", "minimum": 10, "maximum": 300 },
        "max_tokens": { "type": "integer", "minimum": 100, "maximum": 128000 }
      }
    },
    "audit": {
      "type": "object",
      "required": ["level"],
      "properties": {
        "level": { "type": "string", "enum": ["minimal", "standard", "full"] }
      }
    }
  }
}
```

### Schema 校验规则

- **P0**：`script_hooks` 必须为 **空对象** `{}`（不可含 `preprocess` 键）；详见 [34-p0-delivery-spec.md](34-p0-delivery-spec.md)
- **必填字段缺失**：编译阶段直接报错，RunSpec 不生成
- **版本不匹配**：Runner 拒绝执行 `runspec_schema_version` 超出兼容窗口（N=2）的 RunSpec
- **Hash 格式错误**：`skill_package_hash` 必须为 64 位十六进制（sha256）
- **枚举值非法**：`audit.level` 不允许为 `off`

---

## 跟 progressive disclosure 的关系

Skill Package 内部用 progressive disclosure——**这个分层加载就是它的运行时实现**：

| 层 | 时机 | 谁拉 |
|----|------|------|
| 元数据（frontmatter） | 路由 / 发现时 | Agent App 注册中心 |
| 主体（SKILL.md body） | 编译 RunSpec 时 | Skill Compiler |
| always references | 编译 RunSpec 时 | Skill Compiler |
| on_demand references | 模型循环中调 read_reference | Tool Gateway |
| indexed references | 模型调 kb.search | Tool Gateway → 知识服务 |
| scripts | 受控 worker 实际调用时（**P2+**；P0 不部署 Worker，`script_hooks` 为空） | Worker 池 |
| schemas | 输出校验时 | Agent Runner |
