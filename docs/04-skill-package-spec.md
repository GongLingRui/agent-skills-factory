# 04. Skill Package 规范

> 版本：v0.6 · 2026-05-06

---

## 设计思路

Skill 包结构尽量贴近 **Claude 的 Agent Skills 标准**——这样以后想搬到 Claude Code 或 Claude API，迁移成本最低。

**Claude 标准的核心规矩**：

- Skill 是文件系统目录
- 每个 Skill 必有 **SKILL.md**
- 顶部 YAML frontmatter 写元数据
- 元数据常驻上下文用于发现
- SKILL.md 正文按需加载
- 额外 reference / template / example / scripts 按需读

我们叠一层企业治理：**Claude 兼容的核心 + 企业扩展**。

> **标准层（Claude 原生认）**：SKILL.md + references/ + examples/ + templates/ + scripts/
> **企业层（仅本系统读）**：enterprise.yaml + schemas/ + evals/

---

## 推荐目录结构

```
skills/
  clause-review/
    SKILL.md                          # 唯一强制入口
    reference.md                      # 总体方法说明（双兼容；canonical 推荐用 references/）
    examples.md                       # 示例
    references/                       # 配套资源（canonical 目录名）
      checklist.md
      risk-levels.md
    templates/
      standard-clause.md
    schemas/
      clause-risk-item.json
    scripts/
      README.md
      normalize_contract_text.py
      extract_clause_candidates.py
    evals/
      skill_cases.jsonl
    enterprise.yaml                   # 企业治理扩展
```

---

## SKILL.md（给系统和模型看的入口）

```yaml
---
name: clause-review
description: 审查合同关键条款，给风险等级、依据和修改建议。用于合同审查、条款风险识别、法务修改建议、合同模板比对。
when_to_use: 用户上传合同、问条款风险、要法务审查意见、要对照公司模板时使用。
---

# 合同条款审查

你负责审查合同关键条款，包括付款、违约、保密、知识产权、争议解决、不可抗力、终止。

执行要求：

1. 先识别合同类型、主体、金额、期限、关键义务
2. 对关键条款逐项判断风险等级
3. 必须引用公司制度、模板条款或历史案例作为依据
4. 每个风险点必须给出可落地的修改建议
5. 不确定时明确标记"需人工复核"，不要编造依据

## 配套文件

- `reference.md`：审查方法和风险等级说明
- `examples.md`：报告示例和条款修改示例
- `references/checklist.md`：分类型审查清单
- `references/templates/standard-clause.md`：标准条款模板
- `scripts/normalize_contract_text.py`：合同清洗脚本
- `scripts/extract_clause_candidates.py`：候选条款提取脚本
```

### 约束

- `name`：小写字母、数字、连字符
- `description`：同时写清"能做什么"和"什么时候用"
- `when_to_use`：触发条件，避免误触发
- 描述别太宽，否则模型容易误调用

---

## enterprise.yaml（企业扩展，Claude 不读）

放无法塞进 SKILL.md frontmatter、且不适合让模型直接解释执行的治理信息：

```yaml
id: clause-review
version: 0.1.0
owner: legal-department
risk_tier: medium

# risk_tier 映射到系统提示的治理约束
# Skill Compiler 编译时会根据此字段在 prompt_parts 中自动注入对应的治理指令
risk_tier_prompt_map:
  low:
    - "本 Skill 风险等级：低。允许常规操作，无需额外审批提示。"
  medium:
    - "本 Skill 风险等级：中。输出涉及业务判断时，必须标注'需人工复核'。"
    - "引用制度时必须标注文号和生效日期。"
  high:
    - "本 Skill 风险等级：高。所有输出必须标注'需人工复核'，不得替代专业判断。"
    - "涉及金额、期限、权利义务的结论必须列出依据来源。"
    - "不确定时必须明确拒绝回答，禁止编造依据。"

reference:
  load_policy: on_demand
  files:
    - references/checklist.md
    - references/risk-levels.md

tools:
  require:
    - doc.extract
    - kb.search
  optional:
    - risk.rule_check

knowledge_scopes:
  suggest:
    - group_legal_policy
    - contract_templates

schemas:
  output_item: schemas/clause-risk-item.json

evals:
  cases: evals/skill_cases.jsonl

scripts:
  preprocess:
    - id: normalize_contract_text
      entry: scripts/normalize_contract_text.py
      mode: controlled_worker
      timeout_seconds: 10
      network: false
  candidate_extract:
    - id: extract_clause_candidates
      entry: scripts/extract_clause_candidates.py
      mode: controlled_worker
      timeout_seconds: 15
      network: false

limits:
  max_prompt_tokens: 2000
  max_reference_tokens: 4000
```

### risk_tier 与 prompt 映射机制

`risk_tier` 不只是元数据标签，它会**在编译阶段被 Skill Compiler 翻译成具体的系统指令**，注入到 RunSpec 的 `prompt_parts` 中：

| risk_tier | 注入的治理约束 |
|-----------|---------------|
| `low` | 常规风险提示，允许模型自主判断 |
| `medium` | 业务判断必须标注"需人工复核"；引用制度须标注文号 |
| `high` | 所有输出必须标注"需人工复核"；涉及关键字段须列明依据；不确定时必须拒绝 |

**映射配置位置**：`enterprise.yaml` 顶层的 `risk_tier_prompt_map` 字段（见上方示例）。

- 若 Skill 包未配置 `risk_tier_prompt_map`，系统使用**默认映射表**（见 [07-skill-compiler.md](07-skill-compiler.md) §risk_tier 默认映射）
- 业务部门可在 Agent 级覆盖映射（`agent.yaml` → `enterprise.risk_tier_prompt_override`），但**不能删除 high 等级的强制复核要求**

### 为什么 SKILL.md 和 enterprise.yaml 分开

- **可迁移**：以后想搬到 Claude Code，Claude 只读 SKILL.md + 配套文件就够了，企业层忽略
- **可治理**：企业系统能额外读权限、知识域、脚本策略、评测、风险等级

---

## references/ 加载策略

> **命名约定（v0.6 修订）**：canonical 目录名为 **references/**（复数，对齐 Claude / nanobot 主流），系统读取时**双兼容**——references/ 优先，找不到 fallback 到 reference/。新建 Skill 一律用复数。

**根目录 `reference.md` 与 `references/` 目录的优先级**：

- 根目录 `reference.md`（如存在）视为 `load_policy: always`，编译时直接拼进 prompt_parts
- `references/` 目录下的文件按 `load_policy` 处理
- **冲突规则**：若根目录 `reference.md` 与 `references/reference.md` 同时存在，**`references/` 目录优先**，根目录 `reference.md` 被忽略（避免重复加载）

**references/** 放长材料，不该每次都塞进 prompt。三种加载策略：

| 策略 | 说明 | 适用文件类型 | 行为差异 |
|------|------|-------------|---------|
| always | 每次都加载 | `.md`、`.txt`、`.yaml` | 编译时**读取全文**拼进 `prompt_parts`；内容变化触发 RunSpec 重新编译 |
| on_demand | 运行时按需加载 | `.md`、`.txt`、`.yaml`、`.json` | 编译时**只记录路径**进 `lazy_references`；运行时模型调用 `read_reference` 才拉取；内容变化不影响已编译 RunSpec |
| indexed | 进检索索引 | `.md`、`.txt`、`.docx`、`.pdf`（文本可提取格式） | 编译时**只记录 scope** 进 `indexed_references`；知识服务负责提取文本、分块、建索引；内容变化由知识服务侧管理版本 |

**文件类型加载行为详细差异**：

| 文件类型 | always 行为 | on_demand 行为 | indexed 行为 |
|---------|------------|---------------|-------------|
| `.md` | 全文拼进 prompt，保留 markdown 格式 | 全文返回给模型，保留 markdown 格式 | 知识服务提取纯文本后分块索引 |
| `.txt` | 全文拼进 prompt | 全文返回给模型 | 知识服务直接分块索引 |
| `.yaml` / `.yml` | 全文拼进 prompt，作为结构化规则 | 全文返回给模型，Runner 不负责解析 | 知识服务按文本处理 |
| `.json` | 全文拼进 prompt（**不推荐 always**，过长会爆 token） | 全文返回给模型，由模型自行解析 | 知识服务按文本处理 |
| `.docx` / `.pdf` | **不支持 always**（二进制格式无法直接拼 prompt） | **不支持 on_demand**（需先 doc.extract 提取文本） | 知识服务负责 OCR/提取后索引 |

**约束**：

- `always` 策略的文件总 token 数（所有 always references 合计）不得超过 `limits.max_prompt_tokens` 的 50%，超过时 Compiler 报错
- `on_demand` 的 `.docx` / `.pdf` 文件需先通过 `doc.extract` 提取文本后，再由模型调用 `read_reference`——read_reference 本身**不处理二进制文件**
- `indexed` 的文档更新后，知识服务负责重新索引，RunSpec 无需重新编译（indexed references 只存 scope 名）

**口诀**：

> 短规则 → SKILL.md
> 长材料 → references/
> 高频标准 → schema 或规则工具
> 正式制度 → 知识服务

**两条 Claude 兼容性约束**：

- 配套文件必须从 SKILL.md 直接引用，避免多层嵌套引用导致模型只读到局部
- 长 reference 文件应在开头放目录，便于模型按章节按需读

---

## templates/ 加载策略

**templates/** 放输出格式模板、标准条款模板、报告骨架等**可复用的结构化内容**。

| 策略 | 说明 | 示例 |
|------|------|------|
| always | 模板内容编译时直接拼进 prompt | 合同审查报告的固定章节结构 |
| on_demand | 运行时按需读取 | 特定合同类型的专用模板 |
| indexed | 进检索索引，由 kb.search 查 | 大量历史报告模板库 |

**与 references/ 的区别**：

- **references/**：给模型看的**知识材料**（制度、清单、案例）
- **templates/**：给模型用的**格式骨架**（报告结构、条款模板、输出框架）

**使用方式**：

- 在 SKILL.md 中通过 `{{template:standard-clause}}` 或 frontmatter 声明
- Skill Compiler 编译时按 `load_policy` 决定是拼进 prompt 还是只记路径
- Runner 输出 schema 校验时，模板内容可作为"预期结构"参与校验

---

## scripts/ 必须受控

Claude 原生环境里 scripts 可以由 Claude 通过 bash 执行。**本系统不允许这么干**——必须映射成 Tool Gateway 注册的工具，或交给受控 Worker 池跑。

| 类型 | 是否建议 | 说明 |
|------|---------|------|
| build-time（校验、生成 schema、跑 eval） | 强烈建议 | 不在生产环境跑 |
| 预处理 / 后处理（文档清洗、格式转换） | 可以 | **必须受控 worker** |
| Tool 包装脚本 | 可以 | 通过 Tool Gateway 暴露 |
| 任意运行时插件 | **不允许** | 装依赖 / 访问网络 / 自由执行 一律禁 |

**脚本边界（script_policy）**：

```yaml
script_policy:
  dependency_install: false
  network: false
  filesystem: temp_only
  timeout_seconds_default: 10
  max_memory_mb: 512
  audit_input_output: true
  allowed_runtime:
    - python3.11
    - node20
```

---

## 跟 Claude 标准的对应表

| 本方案 | Claude 对应物 | 迁移策略 |
|--------|--------------|---------|
| skills/<name>/SKILL.md | Claude Code / API Skill 入口 | 原样保留 |
| frontmatter | Skill 元数据 | 原样保留 |
| reference.md / examples.md | 配套 markdown | 原样保留 |
| references/（双兼容 reference/） | 配套资源 | 保留，但确保从 SKILL.md 直接引用 |
| scripts/ | 工具脚本 | 保留；迁 Claude API 时要求无网络、无依赖安装 |
| schemas/ | 配套资源或企业校验 | Claude 忽略，本系统用 |
| evals/ | 企业评测集 | Claude 忽略，CI 用 |
| enterprise.yaml | 无对应 | 企业扩展，迁移时忽略 |

---

## 评测集（evals/）格式规范

`evals/skill_cases.jsonl` 是 Skill 入库前的必跑评测集，每行一个 JSON 对象。

### 字段格式

```json
{
  "id": "case_001",
  "name": "合同付款条款审查",
  "input": {
    "message": "请审查以下合同的付款条款：...",
    "files": ["sample_contract.docx"]
  },
  "expected_tags": ["payment_risk", "high"],
  "expected_schema_fields": ["risk_level", "suggestion", "citation"],
  "min_score": 0.8,
  "tags": ["payment", "high_value"]
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 用例唯一标识 |
| `name` | 是 | 用例名称 |
| `input.message` | 是 | 输入用户消息 |
| `input.files` | 否 | 需要附带的测试文件路径（相对 skill 包根目录） |
| `expected_tags` | 否 | 期望输出包含的语义标签（用于自动评分） |
| `expected_schema_fields` | 否 | 期望 JSON Schema 输出中必须包含的字段 |
| `min_score` | 是 | 最低通过分数（0~1） |
| `tags` | 否 | 用例分类标签 |

### 执行机制

1. **触发时机**：Skill Registry 入库流程第 2 步（见下文），作为 schema 校验后的自动环节。
2. **执行环境**：CI 流水线或 Skill Registry 内置评测 Worker（**不消耗生产模型配额**，使用独立评测模型或 mock）。
3. **通过标准**：所有用例的执行分数均 >= `min_score`，且 `expected_schema_fields` 全部命中。
4. **失败处理**：评测不通过 → Skill 包拒绝入库，返回具体失败的 case_id 和原因。

### 与 P0 阶段的关系

P0 阶段 evals 必须存在且 >=1 条，但**允许空跑**（即只校验格式和 schema，不实际调模型评分），以避免阻塞早期 Skill 迭代。P1 起启用完整模型评测。

---

## SKILL.md Frontmatter 与 enterprise.yaml 校验 Schema

Skill Registry 入库时必须校验以下字段合规性。

### SKILL.md Frontmatter Schema

```yaml
---
name: clause-review                    # 必填；小写字母、数字、连字符；长度 3-64
description: "..."                     # 必填；长度 20-500
when_to_use: "..."                     # 必填；长度 20-300
---
```

| 字段 | 类型 | 约束 |
|------|------|------|
| `name` | string | 必填，regex `^[a-z0-9-]+$`，长度 3-64 |
| `description` | string | 必填，长度 20-500 |
| `when_to_use` | string | 必填，长度 20-300 |

### enterprise.yaml 校验 Schema

```yaml
id: clause-review                      # 必填；与 SKILL.md name 一致
version: 0.1.0                         # 必填；semver
owner: legal-department                # 必填
risk_tier: medium                      # 必填；enum [low, medium, high]

reference:
  load_policy: on_demand               # 必填；enum [always, on_demand, indexed]
  files:                               # 必填；相对路径数组
    - references/checklist.md

tools:
  require: []                          # 可选；工具 ID 数组
  optional: []                         # 可选；工具 ID 数组

knowledge_scopes:
  suggest: []                          # 可选；scope 数组

schemas:
  output_item: ""                      # 可选；相对路径

evals:
  cases: ""                            # 必填（P0 允许占位文件）；相对路径

scripts:                               # 可选；P0 阶段被忽略
  preprocess: []

limits:
  max_prompt_tokens: 2000              # 可选；int，>0
  max_reference_tokens: 4000           # 可选；int，>0
```

| 字段 | 类型 | 约束 |
|------|------|------|
| `id` | string | 必填，必须与 SKILL.md frontmatter 的 `name` 一致 |
| `version` | string | 必填，semver |
| `owner` | string | 必填 |
| `risk_tier` | string | 必填，enum [low, medium, high] |
| `reference.load_policy` | string | 必填，enum [always, on_demand, indexed] |
| `reference.files` | [string] | 必填，文件必须在 Skill 包内存在 |
| `evals.cases` | string | 必填（P0 可为空文件），指向的文件必须存在 |

**文件存在性校验**：`reference.files`、`schemas.output_item`、`evals.cases`、`scripts.*.entry` 等所有路径字段，入库时必须校验对应文件在 Skill 包内真实存在。

---

## Skill Registry 接口规范

Skill 包由独立的 Skill Creator 系统产出，通过下面接口入库：

```
POST   /api/v1/skills                     # 注册新 Skill 包（上传 tar.gz / git URL）
PUT    /api/v1/skills/<skill_id>          # 升级 Skill 版本
GET    /api/v1/skills                     # 列出所有 Skill
GET    /api/v1/skills/<skill_id>          # 详情（schema / 版本 / 挂载的 Agent 列表）
DELETE /api/v1/skills/<skill_id>          # 下架（标记 deprecated，不物理删除）
```

### 入库流程

1. Skill Creator 上传 Skill 包
2. Skill Registry 校验：
   - SKILL.md frontmatter schema
   - enterprise.yaml schema
   - scripts 静态分析（无网络 / 无依赖安装）
   - evals/ 必须存在且有 ≥1 用例
3. 通过 → 写入 Skill Registry（数据库 + 对象存储）
4. 通知所有挂载该 Skill 的 Agent 缓存失效

### 热更新 vs 冷部署

- **Skill 包升级（小版本，如 0.1.0 → 0.1.1）** → **热加载**：已运行会话用旧版（RunSpec 已钉死），新会话用新版
- **重大 schema 变更（大版本，如 0.x → 1.0）** → **灰度**：按 agent.yaml 的 skill_version_pin 字段控制
