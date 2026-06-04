---
name: demo-skill
description: 本地联调与冒烟用最小 Skill 包。
when_to_use: 用户启用本 Agent 且任务属于「Demo Skill」职责范围时。
---

# Demo Skill

本目录为 Agent App 内嵌的 **Skill 包**（见 `prd.md` 第 5 节与 `docs/03-agent-app-spec.md`）。
详细角色边界与工具策略以同目录上一级的 `agent.yaml` 为准。

## 执行要点

1. 遵守 `agent.yaml` 中的事实性、合规与输出结构要求。
2. 不确定处明确标注；不编造数据、文号、案例或转写中未出现的内容。
3. 按需使用 `read_reference` / `kb.search` 与 `doc.extract`（若在工具白名单中）。
