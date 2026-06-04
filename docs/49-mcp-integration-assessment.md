# 49. MCP 接入评估（P1）

> 版本：v0.1 · 2026-05-08  
> 目的：满足 [plan.md](../plan.md) §6「MCP 接入评估」与 [34-p0-delivery-spec.md](34-p0-delivery-spec.md) 中 **P0 禁用 / P1 评估** 的落档结论，避免与 [prd.md](../prd.md) 冲突。

---

## 结论摘要

| 维度 | 结论 |
|------|------|
| **P0** | **不启用** MCP Server 作为 Tool 执行路径（与 34 一致）。 |
| **P1 推荐** | 新增业务能力优先通过 **Tool Registry + `http_api`**（见 [09-tool-gateway.md](09-tool-gateway.md)）对接已有内部 REST；Runner 已支持基于环境变量的 URL 前缀白名单（见 [31-configuration-reference.md](31-configuration-reference.md)）。 |
| **何时考虑 MCP** | 需要复用 **桌面/IDE 侧已有 MCP 生态**、或第三方仅暴露 MCP 而非 HTTP 时，再以**独立 Sidecar / 独立进程**接入，避免把 MCP 协议栈塞进 Agent Runner 热路径。 |

---

## 与安全、审计的对齐

- **权限**：无论 MCP 或 HTTP，工具权限须在 **Tool Gateway 硬校验**（[09](09-tool-gateway.md)），不接受仅靠模型自律。
- **审计**：工具调用轨迹仍走既有 minimal 审计链路（[12](12-security-audit.md)）；若引入 MCP，须在适配层落同一套 `tool_id` / 参数脱敏口径。
- **SSRF**：HTTP 类工具须保持 **URL 前缀白名单**；MCP 若落地，须同等约束其可触达的网络范围。

---

## 与 PRD / 对齐文档

- P0 裁剪与「P1 评估」表述：[34-p0-delivery-spec.md](34-p0-delivery-spec.md)、[47-prd-alignment.md](47-prd-alignment.md)。
- 路线图阶段定义：[14-roadmap.md](14-roadmap.md)。

---

**修订**：若后续决策启用 MCP，在本文件追加「架构选项对比（Sidecar vs 进程内）」与「上线前检查项」，并在 [31-configuration-reference.md](31-configuration-reference.md) 增补相应配置项。
