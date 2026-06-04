# 47. 与 PRD 对齐说明（实施真相来源）

> 版本：v0.6 · 2026-05-06

---

## 目的

[prd.md](../prd.md) 为方案原文。**本仓库以 `docs/` 为落代码时的权威细节**——当 PRD 与 docs 出现粒度或历史修订残留不一致时，**以本文档与下列引用为准**，避免实现分叉。

---

## 里程碑：审计「写入」vs「消费」

| 名称 | 含义 | 文档 |
|------|------|------|
| **P0** | **minimal 级审计已写入**（落库：工具轨迹、检索 ID、错误码等）；不允许 `audit.level: off` | [12-security-audit.md](12-security-audit.md)、[34-p0-delivery-spec.md](34-p0-delivery-spec.md) |
| **P0.5** | **审计消费端**：查询面板、导出、简易报表；常与压测、安全加固同学科 | [14-roadmap.md](14-roadmap.md) §P0.5 |

PRD 部分段落仍出现「P0.5 才接最小审计」类**旧口径**，含义实际指 **消费端/看板**，而非首次落库——实现时以本说明为准。

---

## RunSpec 与 P0 裁剪

- **完整字段语义**：[05-runspec.md](05-runspec.md)
- **P0 必须**：`script_hooks` 固定 `{}`，Skill 中运行时脚本声明由 Compiler **忽略且不报错**：[34-p0-delivery-spec.md](34-p0-delivery-spec.md)

---

## P2 / P3（路线图占位与「仅评估」落档）

- **运行时代码**：受控脚本 Worker、`script_hooks` 非空、P3 DAG/Router/**真 multi-skill** 不在当前 P0/P1 里程碑交付；红线见 [34-p0-delivery-spec.md](34-p0-delivery-spec.md) 与仓库 `CLAUDE.md`。
- **计划对账与设计定档**：`plan.md` §7–§8 的收口清单与 multi-skill 评估结论见 **[50-p2-p3-phase-assessment.md](50-p2-p3-phase-assessment.md)**（与 [14-roadmap.md](14-roadmap.md) §P2、§P3 一致）。

---

## Prompt 拼装优先级

PRD 常用一行公式概括；**落地拼装顺序与 enterprise 执行类/策略类拆分**以 Skill Compiler 为准：

→ [07-skill-compiler.md](07-skill-compiler.md) §Prompt 拼装

---

## `max_turns` 语义

**指单次会话内模型调用次数上限**（含工具循环中的多轮 model step），**不是**「用户发送几条用户消息」。UI 提示文案须避免让用户理解为聊天轮数。

→ [05-runspec.md](05-runspec.md) `runtime.max_turns`

---

## 跨会话摘要记忆（服务端）

PRD 10.3 强调**对话全文**默认不落服务端；Runner 另维护 **短文本滚动摘要**（表 ``user_agent_memory``，键为 ``user_id_hash`` + ``agent_id``），用于模型侧连贯，**不是**全文会话存储。可通过 ``limits.context_memory.cross_session_memory_enabled: false`` 关闭。详见 [08-agent-runner.md](08-agent-runner.md) §上下文治理。

---

## PRD 内已知遗留表述（只读提醒）

以下条目存在于 `prd.md` 某段示例或旧句，**请勿当作实施约束**：

| 位置（PRD） | 建议忽略或对照 docs |
|-------------|---------------------|
| §7.2 RunSpec 示例中 `audit.enabled: false` | 与 v0.6「默认 minimal、不允许 off」冲突；以 **RunSpec `audit.level`**（见 [05-runspec.md](05-runspec.md)）为准 |
| §10.6「P0 阶段审计可以暂缓」类表述 | 与 §10.2 冲突；以 **P0 minimal 已开启** 为准 |

---

## RBAC 与系统层校验

门户 JWT 中的 `permissions`（能力码与/或角色名）在服务端展开为 `effective_permissions`；管理类 API 与会话、运维 Bearer 的矩阵见 **[51-rbac-implementation-spec.md](51-rbac-implementation-spec.md)**。Registry `http_api` 工具的 `permission_required` 与调用方展开能力求交，由 Tool Gateway 在 Runner 调用路径上硬校验（与 PRD 系统层校验口径一致）。**阶段 B–D**（管理台菜单、`department_admin` 与 `agent_apps.owner` 对齐、`sync-permissions` / `session-revocations`）以 `docs/51` 正文为准。

---

## 文档内 § 章节号

未额外标注时，正文中的 **§x.x** 均指 **prd.md** 章节编号；对应实现细节优先查阅 `docs/` 映射表（见 [README.md](README.md) 索引）。
