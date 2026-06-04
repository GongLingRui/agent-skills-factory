# Agent App Factory — 未完成任务清单（PRD 对账）

> 版本：v0.7 对账 · 2026-05-15
> 依据：`prd.md` 全文走读 + `plan.md` §12–§13 + 代码库实际文件扫描
> 原则：**不重复罗列已勾选交付项**；已落地模块仅在其存在「余量缺口」时提及。

---

## 1. 策略管理（Policy Registry）— 已落地

| 项目 | 状态 | 落位 |
|------|------|------|
| `GET /policies/platform` | 已实现 | `api/v1/policies.py` |
| `POST /policies/platform` | 已实现 | `api/v1/policies.py` |
| `PUT /policies/platform/{policy_id}` | 已实现 | `api/v1/policies.py` |
| `GET /policies/org/{department}` | 已实现 | `api/v1/policies.py` |
| `POST /policies/org` | 已实现 | `api/v1/policies.py` |
| `PUT /policies/org/{policy_id}` | 已实现 | `api/v1/policies.py` |
| Service 层 | 已实现 | `services/policy_service.py` |
| 前端管理台 | 已实现 | `AdminPoliciesPage.tsx`（CRUD + 版本历史） |

---

## 2. Token 预算管理 — 已落地

| 项目 | 状态 | 落位 |
|------|------|------|
| `GET /admin/token-quotas` | 已实现 | `api/v1/admin.py` |
| `PUT /admin/token-quotas/{scope}/{scope_id}` | 已实现 | `api/v1/admin.py` |
| Service 层 | 已实现 | `services/quota_service.py` |
| 前端管理台 | 已实现 | `AdminQuotasPage.tsx`（列表 + 预算调整弹窗） |

**余量**：Runner 调用后自动 `increment_used_tokens` 需在 chat handler 显式接入（当前 Service 已就绪，调用点视上线策略可选接入）。

---

## 3. 用户与部门管理 — 已落地

| 项目 | 状态 | 落位 |
|------|------|------|
| `GET /admin/users` | 已实现 | `api/v1/admin.py` |
| `PUT /admin/users/{user_id}/roles` | 已实现 | `api/v1/admin.py` |
| `GET /admin/departments` | 已实现 | `api/v1/admin.py` |
| DB 模型 | 已实现 | `db/models/synced_user.py`、`synced_department.py` |
| Service 层 | 已实现 | `services/user_sync_service.py` |
| 前端管理台 | 已实现 | `AdminUsersPage.tsx`（分页 + 部门筛选 + 角色编辑） |

---

## 4. Agent 屏蔽接口 — 已落地

| 项目 | 状态 | 落位 |
|------|------|------|
| `POST /admin/agents/{agent_id}/disable` | 已实现 | `api/v1/admin.py` |
| Redis TTL 屏蔽 | 已实现 | `services/agent_disable.py` |
| 前端管理台 | 已实现 | `AdminAgentsPage.tsx`（临时禁用弹窗） |

---

## 5. 审计档位动态提升 — P0 固定 minimal

| 项目 | 状态 | PRD 出处 |
|------|------|----------|
| 运行时从 `minimal` → `standard` / `full` | P0 不交付 | `docs/34-p0-delivery-spec.md` |
| `standard` / `full` 消费端 | 查询接口已就绪，数据依赖档位提升 | `docs/12-security-audit.md` |

**口径**：P0 强制 `audit.level = minimal`，动态提升属 P1+。

---

## 6. RunSpec 多版本执行器（v2 / N=2 向后兼容窗口）

| 项目 | 状态 | PRD 出处 |
|------|------|----------|
| `runspec_schema_version = 2` 的字段语义与执行器 | P0/P1 仅日志桥接 | `plan.md` §13.1 §7.6 |
| Runner 双执行器桥接 | 已做版本守卫 + INFO 日志 | `services/runner_service.py` |

**口径**：`runspec_schema_version > 1` 时仍按 v1 语义执行并打日志，待 v2 Runner 专项再拆分。

---

## 7. 整包 zip 从 Registry 拉取与按需文件 hash 校验

| 项目 | 状态 | PRD 出处 |
|------|------|----------|
| Skill 整包 zip 存储于 MinIO/S3 | P0 走 inline `reference_files` | `plan.md` §12 |
| 单文件 hash 与包不一致时报错 | 待迭代 | `docs/05-runspec.md` |

---

## 8. 模型网关演进（非阻塞性缺口，属性能优化）

| 项目 | 状态 | PRD 出处 |
|------|------|----------|
| Rerank 独立池与饥饿处理 | 降级中已有 rerank 裁剪，无独立队列 | `prd.md` §9.1–§9.2 |
| `interactive` / `document` / `batch` / `privileged` 队列语义完全对齐 | ZSET 优先级已落地，语义部分对齐 | `plan.md` §13.2 §9.1–§9.2 |

---

## 9. `risk.rule_check` 生产级规则引擎 — 已落地占位 + Service

| 项目 | 状态 | 落位 |
|------|------|------|
| `risk_rule_engine.py` | 已实现 | `services/risk_rule_engine.py` |
| ToolGateway 接入 | 已接入 | `infra/tool_gateway.py` |
| 单元测试 | 已覆盖 | `tests/unit/test_risk_rule_engine.py` |

**口径**：当前为内置规则引擎；若组织有独立风控系统，可配置为 `http_api` Tool 外接。

---

## 10. `kb.search` 外部 HTTP 契约 — 已落地

| 项目 | 状态 | 落位 |
|------|------|------|
| HTTP Client | 已实现 | `services/kb_search_client.py` |
| 单元测试 | 已覆盖 | `tests/unit/test_kb_search_client.py` |

**余量**：`indexed_references` 进入外部向量/索引依赖知识侧集成，本系统已输出元数据。

---

## 11. Skill 包上传管线（tar.gz）— 已落地

| 项目 | 状态 | 落位 |
|------|------|------|
| `POST /skills/upload` | 已实现 | `api/v1/skills.py` |
| tar.gz 解压 + 静态分析 | 已实现 | `services/skill_upload_service.py` |
| AST 黑名单检查 | 已实现 | `skill_upload_service.py` |
| 单元测试 | 已覆盖 | `tests/unit/test_skill_upload_service.py` |

---

## 12. Tool 双签审批 — 已落地

| 项目 | 状态 | 落位 |
|------|------|------|
| `pending_approval` 状态 | 已实现 | `api/v1/tools.py` |
| `POST /tools/{id}/approve` | 已实现 | `api/v1/tools.py` |
| 审批日志表 | 已实现 | `db/models/tool_approval_log.py` |
| 前端审批按钮 | 已实现 | `AdminToolsPage.tsx` |

---

## 13. 前端管理台余量页面 — 已补齐

| 项目 | 状态 | 落位 |
|------|------|------|
| Skill 可视化管理页（CRUD + 上传） | 已实现 | `AdminSkillsPage.tsx` |
| Tool 可视化管理页 | 已实现 | `AdminToolsPage.tsx` |
| 策略管理页 | 已实现 | `AdminPoliciesPage.tsx` |
| Token 预算页 | 已实现 | `AdminQuotasPage.tsx` |
| 用户/部门页 | 已实现 | `AdminUsersPage.tsx` |
| 会话追踪专页 | 已实现（API + JSON 查看） | `AdminSessionTracePage.tsx` |
| 独立 admin JWT 登录 | 后端 `POST /auth/admin-login` 已就绪；前端 Bearer 输入框兼容任意 JWT | `api/v1/auth.py` |

---

## 14. Playwright / Widget E2E 回归测试

| 项目 | 状态 | PRD 出处 |
|------|------|----------|
| Playwright 配置与用例 | 未配置（当前里程碑不纳入） | `plan.md` §4.10 |

**口径**：用户明确「暂时不需要 playwright」。前端以 Vitest 为主。

---

## 15. P2 / P3 运行时代码（项目边界内，但属远期专项）

> 以下项 PRD 已要求，但 `docs/34-p0-delivery-spec.md` 与 `plan.md` §7–§8 明确将其冻结至 P2/P3 专项排期。**当前仓库不交付**。

| 项目 | 状态 | PRD 出处 |
|------|------|----------|
| 受控脚本 Worker 池 | 未交付 | `prd.md` §3.2 / §6.5–§7.7 |
| `script_hooks` 非空执行链路 | 恒 `{}` | `docs/34-p0-delivery-spec.md` |
| Skill 小型 DAG 编排 | 未交付 | `prd.md` §11 P3 |
| Router Agent（可选） | 未交付 | 同上 |
| multi-skill 执行链路 | 仅评估，不交付 | `plan.md` §8 |

---

## 16. 运维与基础设施（非纯代码，但影响交付完整性）

| 项目 | 状态 | PRD 出处 |
|------|------|----------|
| HTTPS + HSTS | 终端 Ingress 配置 | `prd.md` §10.7 |
| JWKS 公钥拉取（portal 验签） | 当前以对称/共享 secret 实现 | `plan.md` §13.2 §10.4 |
| OpenTelemetry Collector / Grafana Tempo | 代码已接入 OTLP/HTTP，环境侧未配 | `plan.md` §13.2 §10.6 |
| 完备业务报表 / 数仓 / BI | 轻量 API 已提供，固定报表产品未建 | `plan.md` §13.2 §10.6 |
| Agent 层 QPS/错误率/P99/token trend 大盘 | 规则 JSON 已提供，需导入 Grafana | `deploy/grafana/dashboards/agent-factory-overview.json` |

---

## 附录：快速核对命令

```bash
# 1. 检查后端已注册路由（与 docs/19-api-reference.md 对照）
grep -rn "@router\." backend/src/agent_factory/api/v1/ | grep -E "(get|post|put|patch|delete)"

# 2. 检查前端管理台页面（与 App.tsx 对照）
grep -rn "Route path=" frontend/src/App.tsx

# 3. 运行后端单元测试（排除 Redis 集成测试）
pytest backend/tests/unit/ -q -k "not (enqueue_dequeue or priority_ordering or queue_length)"

# 4. 前端类型检查
cd frontend && npx tsc --noEmit
```

---

*本文档应随代码迭代同步更新；每完成一项，请在对应行前打勾并记录合并请求编号。*
