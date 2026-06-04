# 50. P2/P3 阶段评估与实施冻结清单

> 版本：v0.1 · 2026-05-09  
> 对应 [plan.md](../plan.md) §7、§8；与 [34-p0-delivery-spec.md](34-p0-delivery-spec.md)、[47-prd-alignment.md](47-prd-alignment.md)、[14-roadmap.md](14-roadmap.md) 一致。

---

## 1. 范围声明（当前里程碑）

| 约束 | 说明 |
|------|------|
| **P0/P1 代码** | `script_hooks` **必须**为 `{}`；**不**部署受控脚本 Worker 池；Skill 包内运行时 `scripts/` 预处理/后处理由 Compiler **忽略且不报错**（见 34）。 |
| **本文档职责** | 将 plan §7–§8 中**尚未写代码**的部分，收敛为 **P2/P3 排期开启后的设计锚点与验收清单**；并完成 **multi-skill「仅评估」** 的结论落档（不扩展为产品承诺）。 |
| **非目标** | 本文不替代 [25-script-worker.md](25-script-worker.md)、[05-runspec.md](05-runspec.md) 的完整设计正文；开工时仍以 25/05 为权威细节。 |

---

## 2. P2：受控脚本与 Tool Gateway（冻结清单）

### 2.1 能力分解（与 plan §7 对账）

| plan 条目 | P2 开工前须对齐的文档 | 备注 |
|-----------|----------------------|------|
| `script_hooks` 非空语义 | [05-runspec.md](05-runspec.md)、[07-skill-compiler.md](07-skill-compiler.md) | Compiler 从「恒 `{}`」改为按 Skill 声明生成；须定义与 P1 评测用 `scripts/` build-time 的边界。 |
| 受控 Worker 池、gVisor、资源配额 | [25-script-worker.md](25-script-worker.md) | 网络策略、tmp、CPU/内存/时长上限、并发度。 |
| 脚本审计 | [12-security-audit.md](12-security-audit.md) | 脚本入参/出参摘要、退出码、超时、与现有 minimal 轨迹的关联键（`run_id` / `session_id`）。 |
| **脚本审计与 Tool Gateway 注册** | [09-tool-gateway.md](09-tool-gateway.md) | 脚本能力以 **受控 tool_id**（或等价注册名）进入 Registry；**硬校验**白名单、参数 schema、与 `http_api` 工具并存时的优先级；禁止旁路 HTTP。 |

### 2.2 与本仓库现状映射（避免重复建设）

| 主题 | 已有落位 | P2 时扩展点 |
|------|----------|-------------|
| 审计异步写入 | `audit_worker`、`push_audit_event`、PG `audit_logs` | 增加脚本专用字段或并行 stream（设计待定，须防日志爆炸）。 |
| Tool 执行总线 | `ToolGateway.validate_and_run_async`、内置 `kb.search` / `doc.extract` / `read_reference` | 增加「脚本类」分支：仅 Worker 回传结果，Runner 不直执行脚本字节码。 |
| 异步队列 | Redis Streams、`mq:*` 模式 | 脚本任务队列 key 命名、死信、与文档解析 Worker 资源隔离。 |
| Compiler | `script_hooks = {}`（P0/P1） | 读取 Skill `scripts` 声明 → 生成 hooks + 版本化 hash；仍须 **拒绝** 任意网络与任意二进制执行路径（见 25）。 |

### 2.3 P2 验收检查表（排期开启后逐条勾选）

- [ ] Compiler 在受控配置下可生成非空 `script_hooks`，且默认关闭（特性开关 + 审批）。
- [ ] Worker 池与 Runner 解耦：Runner 仅下发任务与消费结构化结果。
- [ ] 脚本工具在 Tool Registry 可见，`allowed_tools` 交集与现有逻辑一致。
- [ ] 脚本执行全链路可审计，满足内网合规抽样导出口径。
- [ ] 回滚：一键将 `script_hooks` 生成关闭后，新会话回退为当前 P1 行为。

---

## 3. P3：工作流 Skill、Router、multi-skill（仅评估）

### 3.1 Skill 小型 DAG（设计取向）

- **节点建议类型**：检索子图、单轮生成、工具子调用、人工/门户确认（若组织接入）——须避免 Turing-complete 编排脚本与 Runner 内嵌 DSL 膨胀。
- **与单 Skill 约束**：P0/P1 的「单 Skill Package」可演进为「单入口 Skill + 声明式子步骤」，但 **RunSpec 版本化** 与 **会话钉死** 原则不变（见 [05-runspec.md](05-runspec.md)）。
- **风险**：编排图变更导致审计归因复杂化；须规定每步 `run_id` / span 归属。

### 3.2 可选 Router Agent

- **职责**：按用户意图或元数据选择 **哪一个已发布 Agent App** 承接会话（或 handoff）。
- **与门户关系**：多数内网场景可由 **门户应用目录 + 独立 Widget URL** 完成「路由」，Router 仅在高频多入口合一且需模型侧意图分流时引入。
- **权限**：Router 本身须带最小工具集；被路由 Agent 的 `allowed_tools` 仍各自生效，禁止 Router 放大权限。

### 3.3 multi-skill（评估结论，**不默认承诺**）

与 [prd.md](../prd.md) 边界及 [14-roadmap.md](14-roadmap.md) §P3 一致，结论如下：

| 方案 | 适用 | 主要代价 |
|------|------|-----------|
| **A. 门户编排** | 用户明确进入不同 Widget / 不同 `agent_id` | 无单会话内自动拼多 Skill；实现成本最低，与当前架构一致。 |
| **B. Router Agent（单会话单下游）** | 需在对话中切换「业务域」但统一入口 | 增加 Router 评测与审计；须清晰定义 handoff 与会话状态。 |
| **C. 单会话绑定多 Skill（真 multi-skill）** | 极少数强需求 | RunSpec、权限交集、Tool Registry、审计与 UI 复杂度显著上升；**不作为 P0–P1 承诺**，P3 若推进须单独立项与容量评估。 |

**推荐默认路径**：优先 **A**；若需统一入口再评估 **B**；**C** 仅在有明确业务与合规背书时进入专题设计。

---

## 4. 维护说明

- **[plan.md](../plan.md) §7–§8**：当前里程碑对「运行时代码」不设可勾选任务项（避免与 [34-p0-delivery-spec.md](34-p0-delivery-spec.md) 冲突）；P2/P3 开工后以本文件 §2.3 / §3 为验收锚点，必要时在 plan 中单独立「专项里程碑」章节。
- P2/P3 **代码合入**时：在本文件 §2.3 / §3 勾选或改为链接到「变更请求」编号。
- 与 PRD 冲突时以 [47-prd-alignment.md](47-prd-alignment.md) 为准。

---

**修订记录**：v0.1 初版 — 冻结评估与清单，不引入运行时脚本或多 Skill 执行路径。
