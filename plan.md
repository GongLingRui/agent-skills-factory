# Agent App Factory — 全项目开发计划

> 本文档是 **从需求到交付的执行路线图**：依据 [prd.md](prd.md) 与 [docs/](docs/) 技术文档体系，按阶段拆解任务、标注依赖与验收查阅位置。  
> **约束**：不修改 `prd.md`；口径冲突以 [docs/47-prd-alignment.md](docs/47-prd-alignment.md) 为准。

---

## 1. 目标与非目标（对齐 PRD）

| 目标 | 说明 |
|------|------|
| Agent 应用工厂 | 声明式 `agent.yaml` + **单个** Skill Package → Skill Compiler → **RunSpec** → 共享 Runner / Tool Gateway / 模型队列执行 |
| 私有化与合规 | RBAC、数据域、`minimal` 起审计写入、Tool Gateway 硬校验 |
| 用户入口 | 独立子域 Chat Widget + portal SSO（JWT 短令牌交换） |

**明确不做**（避免范围蔓延）：RAG 本体平台、Skill Creator、multi-skill（P0/P1）、任意插件市场、一人一容器重运行时 —— 详见 [docs/01-overview.md](docs/01-overview.md) §2。

---

## 2. 文档驱动开发的阅读顺序

实施前先锁定下列「必读 → 按模块深入」：

| 次序 | 文档 | 用途 |
|------|------|------|
| 1 | [docs/01-overview.md](docs/01-overview.md)、[docs/02-architecture.md](docs/02-architecture.md) | 边界与模块划分 |
| 2 | [docs/47-prd-alignment.md](docs/47-prd-alignment.md) | PRD 与 docs 口径差异 |
| 3 | [docs/34-p0-delivery-spec.md](docs/34-p0-delivery-spec.md) | **P0 唯一裁剪清单**（script_hooks 空、无脚本 Worker 等） |
| 4 | [docs/19-api-reference.md](docs/19-api-reference.md) | HTTP 契约（前后端对齐） |
| 5 | [docs/05-runspec.md](docs/05-runspec.md)、[docs/07-skill-compiler.md](docs/07-skill-compiler.md)、[docs/08-agent-runner.md](docs/08-agent-runner.md) | 核心执行链路 |

其余文档按当前任务「即用即查」：[docs/README.md](docs/README.md) 索引。

---

## 3. 交付阶段总览（与 docs/14-roadmap.md 一致）

| 阶段 | 周期（估算） | 核心交付 | 验收锚点 |
|------|----------------|----------|----------|
| **P0** | 后端 4–6 周 + 前端 2–3 周并行 | MVP：SSO、注册中心、Compiler、Runner、Tool/模型网关、Widget、minimal 审计**写入** | [docs/34-p0-delivery-spec.md](docs/34-p0-delivery-spec.md) checklist |
| **P0.5** | ~1 周 | 审计**消费端**查询/导出、压测、安全加固 | [docs/14-roadmap.md](docs/14-roadmap.md) §P0.5 |
| **P1** | 3–4 周 | Skill/评测/Tool 深化、内部 API 类 Tool 按需接入 | [docs/14-roadmap.md](docs/14-roadmap.md) §P1 |
| **P2** | 4–6 周 | 受控脚本 Worker、`script_hooks` | [docs/25-script-worker.md](docs/25-script-worker.md) |
| **P3** | 6–8 周 | 工作流 Skill、可选 Router Agent | [docs/14-roadmap.md](docs/14-roadmap.md) §P3 |

---

## 4. P0 实施路线图（最细粒度）

以下顺序兼顾 **依赖**：先有数据模型与配置 → 认证 → Agent/Skill 装载 → 编译与会话 → Runner 与 SSE → 工具与模型 → 前端 → 异步与运维。

### 4.1 基建与仓库骨架

- [x] 后端单体仓库结构对齐 [docs/30-backend-structure.md](docs/30-backend-structure.md)（FastAPI、`api/v1`、core/services/infra/workers）。
- [x] 前端 Widget 核心目录对齐 [docs/29-frontend-structure.md](docs/29-frontend-structure.md)（`src/api`、`stores`、`db`、`components`；侧栏全量组件可按迭代补全）。
- [x] 配置与环境变量清单对齐 [docs/31-configuration-reference.md](docs/31-configuration-reference.md)（`backend/.env.example`、`pip.conf` / `[[tool.uv.index]]`）。
- [x] PostgreSQL schema / Redis / MinIO 按 [docs/17-data-models.md](docs/17-data-models.md)、[docs/20-redis-design.md](docs/20-redis-design.md)、[docs/39-file-pipeline-design.md](docs/39-file-pipeline-design.md) 落地迁移（Alembic，含审计分区与 demo agent 种子）。
- [x] `GET /health`、`GET /ready`、`GET /metrics` 对齐 [docs/19-api-reference.md](docs/19-api-reference.md)、[docs/32-observability-design.md](docs/32-observability-design.md)。

### 4.2 认证与 SSO（portal ↔ widget）

- [x] `POST /auth/exchange`、`POST /auth/session`、`POST /auth/heartbeat`（portal-JWT → short-lived JWT → session cookie，jti 一次性）。
- [x] Session 不绑定 `agent_id`（支持 Agent 切换）；过期权威来源 DB —— [docs/06-api-gateway.md](docs/06-api-gateway.md)。
- [x] 日志与网关 mask URL `token=` —— [docs/46-logging-spec.md](docs/46-logging-spec.md)、[docs/41-nginx-config.md](docs/41-nginx-config.md)（应用层 `TraceAndAccessLogMiddleware`）。

### 4.3 Agent App 注册中心与 Skill 装载

- [x] `agent.yaml` 声明式入库与 **灰度**编排 API（full / canary / pinned；管理 UI 由门户/运营台接入）—— [docs/03-agent-app-spec.md](docs/03-agent-app-spec.md)、`POST/PUT/DELETE /agents`、`POST .../releases`、`GET .../versions`。
- [x] Skill Registry：`GET/POST/PUT/DELETE /skills`（`POST`/`PUT` 可选 `package_metadata` JSONB，Compiler 经 `skill_orm_to_compiler_pkg` 装载）—— [docs/04-skill-package-spec.md](docs/04-skill-package-spec.md)、[docs/19-api-reference.md](docs/19-api-reference.md)。**写操作**：`POST`/`PUT` 使用 `require_skill_publish`，`DELETE` 使用 `require_registry_superuser`；`GET` 会话只读 —— [docs/51-rbac-implementation-spec.md](docs/51-rbac-implementation-spec.md)。
- [x] Tool Registry：`/tools` CRUD —— [docs/09-tool-gateway.md](docs/09-tool-gateway.md)。**`POST`/`PUT`** 使用 `require_tool_admin`；`GET` 会话只读 —— [docs/51-rbac-implementation-spec.md](docs/51-rbac-implementation-spec.md)。
- [x] 预设 Tool 与系统初始化（`scripts/init_db.py` 种子）—— [docs/23-system-init.md](docs/23-system-init.md)。

### 4.4 Skill Compiler 与 RunSpec

- [x] 编译管线（`CompilerService` / `core/compiler.py`）：`prompt_parts`、`allowed_tools`、`retrieval_scopes`、`audit`、`runtime`；**P0 `script_hooks = {}`** —— [docs/07-skill-compiler.md](docs/07-skill-compiler.md)、[docs/34-p0-delivery-spec.md](docs/34-p0-delivery-spec.md)。
- [x] `read_reference` 工具路径与 `skill_package_hash`（RunSpec 字段）—— [docs/05-runspec.md](docs/05-runspec.md)（按需读取由 Tool Gateway 执行）。
- [x] `platform_policy` / `org_policy` 自 PG 加载合并 —— [docs/07-skill-compiler.md](docs/07-skill-compiler.md)（见 `compiler_service`）。

### 4.5 Agent Runner、会话与 SSE

- [x] `POST .../init`：session、run_id、编译 RunSpec；**写 MAU** —— [docs/19-api-reference.md](docs/19-api-reference.md)。
- [x] `POST .../chat`：SSE（text / tool_call / tool_result / done / error）—— [docs/08-agent-runner.md](docs/08-agent-runner.md)。
- [x] 多轮上下文、checkpoint、`resume` —— [docs/08-agent-runner.md](docs/08-agent-runner.md)。
- [x] Schema 校验与重试（JSON 输出场景）—— [docs/08-agent-runner.md](docs/08-agent-runner.md)。
- [x] Session lock（Redis）；有界等待与超时 —— [docs/08-agent-runner.md](docs/08-agent-runner.md)、`SESSION_CHAT_LOCK_*`。

### 4.6 Tool Gateway 与模型网关

- [x] Tool 执行路径：`kb.search`、`doc.extract`、`read_reference`（P0 清单 [docs/34-p0-delivery-spec.md](docs/34-p0-delivery-spec.md)）。
- [x] 权限白名单与基础限流；Registry **`http_api`** **Redis 熔断**（`TOOL_HTTP_CIRCUIT_*`、`tools.rate_limit.circuit_breaker`）—— [docs/09-tool-gateway.md](docs/09-tool-gateway.md)、[docs/31-configuration-reference.md](docs/31-configuration-reference.md)。
- [x] **完整 RBAC（阶段 A–D）**：`core/rbac.py`、`deps_admin`、Runner→Tool Gateway `caller_permissions`；**B** 管理台 `AdminLayout` 按 `GET /auth/me` 能力过滤侧栏（Bearer 仍全量）；**C** `department_admin` 按 `AgentApp.owner == session.department` 约束注册中心与 `GET/PATCH /admin/agents`；**D** `sessions.permissions` / `revoke_gen_seen`、`POST /auth/sync-permissions`、`POST /admin/session-revocations`、`RBAC_PERMISSION_CACHE_SECONDS` 披露 —— [docs/51-rbac-implementation-spec.md](docs/51-rbac-implementation-spec.md)（Alembic `20260512_0001`）。
- [x] 模型路由与 fallback（`model_gateway` / `models.yaml`）；队列 Worker 骨架 —— [docs/10-model-gateway.md](docs/10-model-gateway.md)。
- [x] 文档解析 Worker；大文件上传 **`DOC_PARSE_ASYNC_MIN_BYTES`** 投递 **`mq:doc_jobs`** —— [docs/24-document-parser-worker.md](docs/24-document-parser-worker.md)、`infra/doc_queue.py`。

### 4.7 审计、队列、降级与定时任务

- [x] minimal 审计异步写入（Redis Stream → PG，`audit_worker`）—— [docs/12-security-audit.md](docs/12-security-audit.md)。
- [x] 全局降级等级与运维 API（`/admin/degradation/*`）—— [docs/13-concurrency.md](docs/13-concurrency.md)。
- [x] Cron 调度骨架（`cron_scheduler`）；生产 CronJob 见 K8s 清单 —— [docs/21-cron-jobs.md](docs/21-cron-jobs.md)。

### 4.8 Chat Widget（前端）

- [x] 路由 `/apps/:agentId`、token 换取 session、移除 URL token —— [docs/11-chat-widget.md](docs/11-chat-widget.md)。**`GET /agents`**：portal `allowed_agents` 经短 JWT + `sessions.allowed_agents` 持久化后按列表过滤（prd §4.5.5）。
- [x] `POST` SSE（fetch + ReadableStream）—— [docs/29-frontend-structure.md](docs/29-frontend-structure.md)。
- [x] 分层存储：localStorage（收藏/最近）、IndexedDB（对话快照 Dexie）—— [docs/11-chat-widget.md](docs/11-chat-widget.md)。
- [x] 顶栏 Agent 切换、`GET /agents`、`POST .../init` —— [docs/11-chat-widget.md](docs/11-chat-widget.md)。
- [x] 收藏 / 最近（LRU≤10）—— PRD §4.5.6。
- [x] 文件上传链路；**`ui_config.attachments`**（`attachment_policy.py` / `attachmentPolicy.ts`）—— [docs/39-file-pipeline-design.md](docs/39-file-pipeline-design.md)。
- [x] 反馈 `POST /feedback` + UI —— [docs/19-api-reference.md](docs/19-api-reference.md)。
- [x] `navigator.sendBeacon` → `POST /metrics/frontend` —— [docs/32-observability-design.md](docs/32-observability-design.md)。

### 4.9 入口与集成

- [x] portal 宿主页集成参考（`window.open` + URL 拼装示例）—— [examples/portal-widget-host.html](examples/portal-widget-host.html)；正式门户仍对接自有工程；后端 `POST /auth/exchange` 已就绪 —— [prd.md](prd.md)、[docs/06-api-gateway.md](docs/06-api-gateway.md)。
- [x] CORS：`ALLOWED_ORIGINS` —— [docs/06-api-gateway.md](docs/06-api-gateway.md)。

### 4.10 P0 质量闸门（交付前必过）

- [x] [docs/34-p0-delivery-spec.md](docs/34-p0-delivery-spec.md) **裁剪项**：Compiler/`script_hooks`/审计默认等已由代码 + `test_p0_delivery_spec.py` 锁定；**验收 checklist** 中联调/Staging/安全条目仍为人工签收（文档 §与本仓库实现的对应）。
- [x] [docs/27-testing-strategy.md](docs/27-testing-strategy.md)：后端 pytest 核心单元 + 集成；前端 Vitest（当前里程碑**未**纳入 Playwright）。
- [ ] （可选）Widget **Playwright** 或等价浏览器回归 —— 与 §12、§13.2「docs/27」行一致；采纳后再勾选。
- [x] [docs/43-code-guidelines.md](docs/43-code-guidelines.md)、[docs/46-logging-spec.md](docs/46-logging-spec.md)：CI（ruff + pytest + 迁移 + DB 冒烟）、可选 `.pre-commit-config.yaml`、根目录 `alembic.ini`；结构化日志与 token mask 见既有中间件（46 持续迭代）。
- [x] [docs/37-production-checklist.md](docs/37-production-checklist.md) **首次上线评审**：签字模板见 [docs/p0-production-review-template.md](docs/p0-production-review-template.md)（细则仍以 37 为准）。

---

## 5. P0.5（审计消费端与加固）

- [x] `GET /audit/logs`、`GET /audit/logs/export`（CSV）、`GET /audit/stats/daily`、`GET /audit/stats/daily/export`（CSV）、`GET /audit/sessions/{session_id}/trace`（Bearer `ADMIN_API_TOKEN`）——后端已就绪。
- [x] **管理台（docs/33）前端（MVP）**：[`AdminLayout`](frontend/src/components/layout/AdminLayout.tsx) + `/admin/agents|audit|degradation|metrics`；审计列表/CSV 导出、降级、产品指标走侧栏 **`ADMIN_API_TOKEN`**（sessionStorage）。**未覆盖**：Skill·Tool 可视化管理页、会话追踪专页、独立 admin JWT、用户/部门/Token 预算等 —— [docs/33-admin-dashboard-design.md](docs/33-admin-dashboard-design.md)、§13.2。
- [x] 压测与容量基线 —— [docs/27-testing-strategy.md](docs/27-testing-strategy.md)、[docs/18-deployment-ops.md](docs/18-deployment-ops.md)；落地 [docs/48-p0.5-load-security-baseline.md](docs/48-p0.5-load-security-baseline.md)（`test_health_load_smoke.py`、可选 `scripts/benchmark_health_smoke.py`）。
- [x] 安全加固与渗透复测项 —— [docs/45-security-architecture.md](docs/45-security-architecture.md)；基线与清单 [docs/48-p0.5-load-security-baseline.md](docs/48-p0.5-load-security-baseline.md)、`test_security_headers.py`。

---

## 6. P1（深化）

- [x] SKILL.md YAML frontmatter 解析与校验（`backend/src/agent_factory/core/skill_frontmatter.py`、仓库扫描 `backend/scripts/validate_skill_md_files.py`、CI 步、pytest）；**enterprise 深度合并**（`enterprise_merge.py` + `resolve_risk_tier_prompt`，对齐 [docs/07-skill-compiler.md](docs/07-skill-compiler.md)）；**评测集 JSONL 格式**（`eval_jsonl.py` + `scripts/validate_eval_jsonl.py`，对齐 [docs/04-skill-package-spec.md](docs/04-skill-package-spec.md) §评测集，CI 步）；**离线评测执行与自动评分**（`core/eval_scoring.py`、`scripts/run_skill_eval.py`，复用 `ModelGateway`，对齐 [docs/04-skill-package-spec.md](docs/04-skill-package-spec.md)、[docs/27-testing-strategy.md](docs/27-testing-strategy.md)）。
- [x] **CI 门禁跑评测管线（不调模型）**：`.github/workflows/ci.yml` 已串联 `scripts/validate_eval_jsonl.py` 与 `scripts/run_skill_eval.py --dry-run`（样例 [`examples/evals/skill_cases.jsonl`](examples/evals/skill_cases.jsonl)）；实跑打分仍用 `run_skill_eval.py` + `ModelGateway`（见 §12）。
- [x] **Skill Registry 入库评测门禁**：`POST`/`PUT /skills` 在 `package_metadata.eval_cases`（或 `evals_inline`）非空时做格式校验（失败拒收）；可选 **`SKILL_EVAL_GATE_LIVE=true`** + **`SKILL_EVAL_GATE_MODEL`**（空则用 `models.yaml` 的 `defaults.model`）走实调与 `eval_scoring` —— `services/skill_eval_gate.py`、`services/eval_chat.py`，对齐 [docs/04-skill-package-spec.md](docs/04-skill-package-spec.md)、[docs/27-testing-strategy.md](docs/27-testing-strategy.md)。
- [x] **评测入库实调的 RPM 隔离**：`SKILL_EVAL_GATE_RPM`（0 则取 gate 模型在 `models.yaml` 的 `rpm`）+ Redis 固定窗口计数键 `rl:eval_gate:*`（与入口 `rl:ip:*` 分离）；在线对话仍走 Runner / 模型网关原路径 —— `skill_eval_gate.py`、`ModelGateway.rpm_for()`；多租户细分 RPM 仍可叠加网关侧策略，见 [docs/10-model-gateway.md](docs/10-model-gateway.md)。
- [x] 内部 API 类 Tool：`tools` 表 `implementation.type=http_api` 由 Runner 调用 `ToolGateway.validate_and_run_async` 执行（`INTERNAL_HTTP_TOOL_URL_PREFIXES` / `INTERNAL_HTTP_TOOL_BEARER_TOKEN`，见 [docs/31-configuration-reference.md](docs/31-configuration-reference.md)）；**内置** `kb.search` / `doc.extract` / `read_reference` 仍优先走代码内处理器。新增业务接口按需在 Registry 登记端点 —— [docs/09-tool-gateway.md](docs/09-tool-gateway.md)。
- [x] MCP 接入评估（P0 仍禁用）—— [docs/49-mcp-integration-assessment.md](docs/49-mcp-integration-assessment.md)、[docs/34-p0-delivery-spec.md](docs/34-p0-delivery-spec.md)。

---

## 7. P2（受控脚本）

> **说明**：以下为后续路线图占位，与 [docs/34-p0-delivery-spec.md](docs/34-p0-delivery-spec.md) 的 P0/P1 边界区分；当前里程碑**不**在本仓库交付受控脚本 Worker（`script_hooks` 仍恒 `{}`，见 [docs/47-prd-alignment.md](docs/47-prd-alignment.md)）。

- [x] **设计定档与清单**（替代本阶段运行时交付）：`script_hooks` 非空、受控 Worker 池、gVisor/资源约束、脚本审计与 Tool Gateway 注册的 **P2 开工检查表与现状映射** —— [docs/50-p2-p3-phase-assessment.md](docs/50-p2-p3-phase-assessment.md) §2；权威细节仍以 [docs/25-script-worker.md](docs/25-script-worker.md)、[docs/05-runspec.md](docs/05-runspec.md)、[docs/09-tool-gateway.md](docs/09-tool-gateway.md) 为准。

**运行时代码（不纳入本仓库当前里程碑的可勾选项）**：受控 Worker 池、`script_hooks` 非空生成、脚本工具注册等须在 **P2 专项排期** 单独立项；跟踪入口见 [docs/50-p2-p3-phase-assessment.md](docs/50-p2-p3-phase-assessment.md) §2.3，避免与 P0/P1 `script_hooks={}` 实现分叉。

---

## 8. P3（工作流与 Router）

> **说明**：后续路线图占位；multi-skill / Router 以 PRD 边界为准；评估结论已落档，**不**扩展为 P0/P1 产品承诺。

- [x] **设计评估与选项**（含 DAG / Router 取向）： —— [docs/50-p2-p3-phase-assessment.md](docs/50-p2-p3-phase-assessment.md) §3、[docs/14-roadmap.md](docs/14-roadmap.md) §P3。
- [x] **multi-skill 仅评估**（结论：默认门户多入口；Router 按需；真 multi-skill 单独立项） —— [docs/50-p2-p3-phase-assessment.md](docs/50-p2-p3-phase-assessment.md) §3.3、[prd.md](prd.md) §3。

**运行时代码（不纳入本仓库当前里程碑的可勾选项）**：Skill 小型 DAG、可选 Router Agent、multi-skill 执行链路等须在 **P3 专项排期** 单独立项；取向与选项见 [docs/50-p2-p3-phase-assessment.md](docs/50-p2-p3-phase-assessment.md) §3。

---

## 9. 横切能力（各阶段持续）

| 主题 | 文档 |
|------|------|
| CI/CD、镜像、迁移、回滚 | [docs/28-cicd.md](docs/28-cicd.md) |
| K8s / Ingress / Nginx | [docs/40-k8s-manifests.md](docs/40-k8s-manifests.md)、[docs/41-nginx-config.md](docs/41-nginx-config.md) |
| 备份与灾备 | [docs/22-data-archiving.md](docs/22-data-archiving.md)、[docs/42-disaster-recovery.md](docs/42-disaster-recovery.md) |
| 数据归档与 retention gate | [docs/21-cron-jobs.md](docs/21-cron-jobs.md)、[docs/16-risk-mitigation.md](docs/16-risk-mitigation.md) |
| 故障排查 | [docs/36-troubleshooting.md](docs/36-troubleshooting.md) |
| 本地快速启动 | [docs/35-quickstart.md](docs/35-quickstart.md)、[`scripts/bootstrap-dev.sh`](scripts/bootstrap-dev.sh) |

---

## 10. 建议的迭代节奏

1. **每周**对照 [docs/14-roadmap.md](docs/14-roadmap.md)、本文 §4、**§12** 对账表与 **§13**（PRD 缺口）；阻塞项记入 [docs/36-troubleshooting.md](docs/36-troubleshooting.md) 模板。
2. **每个合并请求**至少覆盖：契约 [docs/19-api-reference.md](docs/19-api-reference.md) 或迁移版本号；涉及 P0 行为时复核 [docs/34-p0-delivery-spec.md](docs/34-p0-delivery-spec.md)。
3. **首批 Agent**（制度问答、合同审查等）：迁移种子与离线声明见仓库 [`agents/`](agents/)（与 `POST /api/v1/agents` 对齐），驱动端到端验收；路线图仍见 [docs/14-roadmap.md](docs/14-roadmap.md)。

---

## 11. 第一批业务 Agent 样本（上线验收用）

- [x] 参考 [docs/14-roadmap.md](docs/14-roadmap.md)：迁移种子 **`policy-qa-agent`**（制度问答）、**`contract-review-agent`**（合同审查），与 **`demo-agent`** 一并用于列表 / 编译 / 端到端验收（验证 kb.search、doc.extract、权限域与审计字段）；另见 prd.md §12 三样例 **`meeting-minutes-agent` / `material-draft-agent` / `public-opinion-brief-agent`**（Alembic `20260508_0007` + `agents/*/agent.yaml`）。

---

## 12. 后续迭代与已知缺口（与代码对账）

避免与既有实现重复建设：下列项在 §4 正文中已标注「待增强」或分期交付，落地前先查 **已有模块**。

| 主题 | 已有落位 | 未建 / 下一手 |
|------|----------|----------------|
| Session 并发排队（非简单 429） | `session_lock`：`ACQUIRE_IF_QUEUE_EMPTY_V1` / `ENQUEUE_WAITER_V1`（Lua）、`queue:session:*` FIFO、`POST .../chat`；`SESSION_CHAT_LOCK_*` | **已落地** FIFO + 有界等待 + 超时；跨会话全局公平仍属网关演进 |
| Tool 熔断细化 | `infra/tool_circuit_breaker.py`、`ToolGateway`、`TOOL_HTTP_CIRCUIT_*`、`tools.rate_limit.circuit_breaker` | **已落地**；跨租户权重等属网关演进 |
| 大文件解析异步 | `doc_queue`、`DOC_PARSE_ASYNC_MIN_BYTES`、`document_parser_worker`；`core/document_text_extract.py`（text / PDF-pypdf / DOCX-PPTX-XLSX zip+XML）；提取文本写入 MinIO `temp/{session}/extract_{file_id}.txt` 与 `extracted_text_path`；`doc.extract` 在 `validate_and_run_async` 读回 | **已落地** 基础文本提取链（xlsx 为按 sheet 拼接的纯文本，无公式/结构化表格语义）；OCR / 复杂表格等仍按 docs/24 迭代 |
| `ui_config.attachments` 精细化校验 | 后端 `attachment_policy.py`（`content_head`）；前端 `attachmentPolicy.ts`（`sniffMimeMagic` / `validateLocalAttachment` 异步读头）与 InputBar；`POST .../upload` | **已落地**（前后端 MIME 魔数对齐）；更深抽检策略可迭代 |
| 离线评测 | `eval_jsonl.py`、`eval_scoring.py`、`validate_eval_jsonl.py`、`run_skill_eval.py`、`skill_eval_gate.py`（含入库实调 RPM：`SKILL_EVAL_GATE_RPM`、`rl:eval_gate:*`）；CI：`examples/evals/skill_cases.jsonl` + `--dry-run` | 多租户 / 部门级 token 预算与独立推理集群仍属运维与网关演进（docs/10） |
| Skill `read_reference`（按需引用） | `core/read_reference.py`；`ToolGateway._handle_read_reference_async` + `validate_and_run_async(..., run_spec=...)`；`RunnerService` 传入 RunSpec；正文来源：`lazy_references` 条目的 `content` 或 `package_metadata.reference_files`；可选 `skill_file_manifest` SHA-256 校验 | **已落地** P0 链；整包 MinIO zip 拉取仍属迭代 |
| 观测样例（Prom / Grafana） | `infra/prometheus_*`、`main.py` `/metrics`（与 Instrumentator 共用 `METRICS_REGISTRY`） | **已提供** 规则与大盘 JSON：[`deploy/prometheus/rules/agent_factory.rules.yml`](deploy/prometheus/rules/agent_factory.rules.yml)、[`deploy/grafana/dashboards/agent-factory-overview.json`](deploy/grafana/dashboards/agent-factory-overview.json)；CI **`observability-samples`**：`promtool check rules` + JSON 校验（`.github/workflows/ci.yml`）。导入后按环境调阈值 |
| OpenTelemetry（可选 traces） | `infra/otel.py`、`OTEL_*`、`pyproject` **`observability`** extra；`create_app` 末尾 `setup_opentelemetry` | **已落地** OTLP/HTTP 导出 + FastAPI 插桩；默认关闭；Collector / Grafana Tempo 仍属环境配置 |
| 业务报表聚合（轻量 API） | `GET /api/v1/admin/product-metrics/summary`、`services/product_metrics.py`（DAU 按日、滚动 MAU 代理、新会话、新 Agent、反馈） | **已落地** 管理端 JSON；与 **`daily_stats`** / 数仓 **互补**，非替代完备报表产品 |
| P2 受控脚本 | Compiler 侧 `script_hooks` 恒 `{}`（P0/P1）；**阶段评估与冻结清单** [docs/50-p2-p3-phase-assessment.md](docs/50-p2-p3-phase-assessment.md) §2 | [docs/25-script-worker.md](docs/25-script-worker.md) |
| P3 工作流 / Router | **评估结论**见 [docs/50-p2-p3-phase-assessment.md](docs/50-p2-p3-phase-assessment.md) §3 | [docs/14-roadmap.md](docs/14-roadmap.md) §P3 |
| **`GET /agents` 列表 RBAC** | `list_agents` + `UserContext.allowed_agents`；portal claim → 短 JWT → `sessions.allowed_agents`（Alembic `20260511_0001`） | **已落地**；portal 不传 `allowed_agents` 时行为与旧版一致（不额外收紧） |
| **Skill/Tool Registry 写权限** | `require_registry_*` 已用于 Skill `POST`/`PUT`/`DELETE`、Tool `POST`/`PUT` | **已落地**；`GET` 仍为会话只读 |
| **外部知识检索 `kb.search`** | 配置 **`KB_SEARCH_URL`** 时 `POST` 上游 JSON（`query`、`retrieval_scopes`、`scope`）；响应须含 **`results`** 列表；失败回退 stub | 契约与字段映射仍可按对接系统迭代；见 `backend/.env.example` |
| **管理后台 UI（审计等）** | §5 MVP：导航 + 审计 + 降级 + 指标 | **余量**见 §5：Skill/Tool 页、会话 trace UI、独立 admin 认证 |
| **Playwright / Widget E2E** | 前端以 Vitest 为主；仓库内 **无** Playwright 配置 | [docs/27-testing-strategy.md](docs/27-testing-strategy.md) 若要求浏览器级回归则单列 |

---

## 13. PRD 对照：尚未在本仓库落地的需求点

> 来源：[prd.md](prd.md) 全文走读 + 与代码对账。下表为 **PRD 要求 versus 本仓库** 的缺口清单（含「刻意不做」边界内的远期项）。**不重复** §4–§11 已勾选交付的正向复述；与 §12 对账表重复的条目保留一处摘要并交叉引用。PRD 与 `docs/` 口径冲突时以 [docs/47-prd-alignment.md](docs/47-prd-alignment.md) 为准。

### 13.1 本迭代已回填（与 §13 原表对账）

| PRD 位置 | 落位摘要 |
|----------|-----------|
| §4.5.4 | 可折叠**侧栏** `HistorySidebar.tsx`（Dexie 列表、选会话恢复）、**导出/导入** `historyBackup.ts`；顶栏 **用户 hint** `GET /auth/me` + **关闭** `window.close()`；**快捷指令** `ui_config.quick_actions` → `InputBar` |
| §4.5.6 | **收藏 / 最近 / 全部** 分区与最近 **相对时间**（`recentAt` + `formatRelativeTime`）；收藏 **↑↓**（`moveFavorite`）+ **拖拽排序**弹层（`FavoritesReorderModal` / `reorderFavorites.ts`） |
| §7.5 | 模型流式 **`usage`** 达 `max_tokens` 比例阈值 → SSE **`usage_warning`**（`runner_service`）+ Widget 横幅 |
| §7.6（桥接） | `run_spec.runspec_schema_version > 1` 时 **仍按 v1 语义执行** 并打 **`INFO` 日志**（`runner_service`），待 v2 Runner 再拆分 |
| §9.5（部分） | **降级提示**：`POST .../init` 与 **chat SSE 首包** 下发 `degradation`；`widget_degradation_hint`；`ChatPage` 横幅。**运行时闭环**：`workers/degradation_auto.py` + Redis 信号；`/metrics` 含 `af_degradation_level` 等（§13.2）。**运维侧样例**：[`deploy/prometheus/rules/agent_factory.rules.yml`](deploy/prometheus/rules/agent_factory.rules.yml)、[`deploy/grafana/dashboards/agent-factory-overview.json`](deploy/grafana/dashboards/agent-factory-overview.json)；告警路由 / Alertmanager 仍属环境配置 |
| §10.3 | **30 天** Dexie 清理 `purgeExpiredChatHistory`；**共享电脑** 文案 + **退出清除** 勾选（`beforeunload`）；**SubtleCrypto** 可选：`lib/localCrypto.ts` + `chatHistorySecure.ts` + `GET /auth/me` 的 `user_id_hash` 派生 AES-GCM；`ChatPage` 勾选 |
| §10.5–§15.1 | **`retention_mau.run_mau_retention_gate`** + `cron_scheduler` 夜间调用；**`MAU_RETENTION_GATE_ENABLED` 默认 `false`**（生产显式打开）；`enterprise_config.mau_threshold` 可读 |
| §10.7 | `index.html` 已含 **CSP**；补 **`<meta name="referrer" content="no-referrer">`**；HSTS 仍属网关 |
| §6.4 | `read_reference`：`reference/` / `references/` **路径候选**与 `resolve_reference_text` **互 fallback** |
| prd.md §12 | Alembic **`meeting-minutes-agent` / `material-draft-agent` / `public-opinion-brief-agent`**（绑定 demo-skill；`mau_threshold:0` 防误 cold） |
| §11.5（部分） | **灰度 / 版本**：`release.strategy`（full / canary / pinned）、`canary.target_departments` / `percent` / `target_users`；**历史版本修剪** `agent.max_versions_keep`（默认保留约 10 个）——见 `agent_registry_service` |
| §6 / §8.5 | **`risk.rule_check`**：ToolGateway 内置占位实现（`tool_gateway._handle_risk_rule_check`）；`init_db` 种子已登记该 Tool |
| §8.5 | **入库至少一条评测**：`SKILL_EVAL_CASES_REQUIRED`（默认 `true`）；`run_skill_registry_eval_gate` 空则 `EVAL_CASES_REQUIRED`；**`demo-skill` 元数据**由 Alembic `20260509_0008` 写入 `eval_cases`；开发/导入可设 `SKILL_EVAL_CASES_REQUIRED=false` |
| §8.5 步骤 4 | Skill 变更 **Redis 通知**：`af:skill:updated` + JSON 负载（`infra/skill_notify.py`；`POST`/`PUT`/`DELETE` /skills 后 `publish_skill_changed`） |
| §9.5（默认阈值） | **自动降级**：`DEGRADATION_AUTO_ESCALATE_ERROR_RATE` 默认 **0.05**、`DEGRADATION_AUTO_LATENCY_ESCALATE_MS` 默认 **30000**（对齐 prd §9.5 文案）；完整阶梯动作（rerank/top_k 等）仍依 `degradation_service` 与运维配置 |
| §10.6 | **前端 beacon → Prometheus**：`af_frontend_events_total{event_type,agent_id}`（`POST /metrics/frontend`）；Widget **`ui_config_render_ok`**（`ChatPage` sendBeacon） |
| §10.7 | **第三方分析 SDK 门禁**：[`scripts/check_widget_third_party.py`](../scripts/check_widget_third_party.py) 扫描 `frontend/package.json`；CI **Widget third-party dependency guard** |

### 13.2 PRD 缺口总表（分期 / 部分落地 / 组织依赖）

| PRD 位置 | 需求要点（摘要） | 现状与缺口 | 建议落位 / 备注 |
|----------|------------------|------------|-----------------|
| §4.5.5 | **`GET /agents` 按 portal `allowed_agents` 过滤** | **已落地**：短 JWT 携带列表 → `sessions.allowed_agents`（JSONB）+ Redis 会话缓存；`UserContext.allowed_agents` | `auth_service`、`agents.list_agents`、Alembic `20260511_0001` |
| §8.5 | Skill **详情含挂载 Agent 列表** | **已落地**：`GET /skills/{id}` 含 `mounted_agents`（`skill_config.id` 反查 `agent_apps`） | `api/v1/skills.py` |
| §8.5–§8.6 | Tool / Skill Registry **写操作鉴权** | **已落地**：`POST`/`PUT`/`DELETE` skills、`POST`/`PUT` tools → `require_registry_*` | `deps_admin` |
| §4 / §6.4 | **`kb.search` 外部 HTTP** | **`KB_SEARCH_URL`** 配置则 `POST` 上游；响应需 `results: []`；否则 stub | `tool_gateway`、`settings`、`backend/.env.example` |
| §6 / §8 | **`risk.rule_check` 生产规则引擎** | **占位 Tool**（demo 返回） | 伙伴风控 HTTP；见 §13.1 已落地「占位」行 |
| §33（设计） | **管理后台** | **MVP 已落地**（§5）；余量：Skill/Tool 页、会话 trace、独立 admin JWT 等 | `frontend/src/components/layout/AdminLayout.tsx` 等 |
| docs/27 | **Chat Widget E2E（Playwright）**（若团队采纳该策略） | 仓库 **未配置** Playwright；与 §4.10「Vitest 为主」并存为**可选缺口** | 按需 `pnpm exec playwright test` |
| §2 | **明确不做**：RAG 本体平台、Skill Creator、P0/P1 multi-skill、插件市场等 | **刻意不实现**（边界声明） | [docs/01-overview.md](docs/01-overview.md)、[prd.md](prd.md) §2 |
| §3.2 / §6.5–§7.7 | Skill `scripts/` **运行时**预处理与 **受控 Worker**、`script_hooks` 非空 | P0/P1：`script_hooks={}`；无 Worker 池 | [docs/34-p0-delivery-spec.md](docs/34-p0-delivery-spec.md)、[docs/25-script-worker.md](docs/25-script-worker.md)、plan §7、[docs/50-p2-p3-phase-assessment.md](docs/50-p2-p3-phase-assessment.md) §2 |
| §6.4 | **`indexed`** references 进检索索引（与 **kb.search** 管线深度打通） | Compiler 有 **`indexed_references` 元数据**；是否全程进入外部向量/索引依赖知识侧集成 | [docs/04-skill-package-spec.md](docs/04-skill-package-spec.md)、知识服务 |
| §7.6 | RunSpec **schema 多版本**与 Runner **向后兼容窗口 N=2**（v2 字段语义 + 双执行器） | v1 已跑通；`>1` **仅日志桥接**（§13.1） | [docs/05-runspec.md](docs/05-runspec.md) |
| §7.7 | **按需文件与包级 hash**：PRD 文案「单文件 hash 与包不一致即报错」；**整包 zip** 从 Registry 拉取 | **inline `reference_files` + `skill_package_hash`** 已用于鉴权；整包对象存储 zip **仍迭代**（另见 §12 表） | [docs/05-runspec.md](docs/05-runspec.md) |
| §8（步骤） | 输出 **schema 校验**（工业级 pydantic-ai 式）；§9 审计「接口位」表述 | Runner 侧 schema 校验 **按 docs 裁剪实现**；非 pydantic-ai 内核 | [docs/08-agent-runner.md](docs/08-agent-runner.md) |
| §8.5 | Skill **tar.gz / git URL** 上传入库、**scripts 静态分析**（无网络/无依赖安装） | Registry 主路径为 **API + `package_metadata` JSONB**；无上传解压管线 | PRD §2 非 Skill Creator；若要做单列「包上传」工程 |
| §8.6 | Tool **双签审批**、仅平台管理员可写 | **实现为特权 API**；双签属 **组织流程** | 门户/工单 |
| §9.1 | **脚本 worker 池**（与 LLM/解析并列的资源行） | **P2** | [docs/25-script-worker.md](docs/25-script-worker.md) |
| §9.1–§9.2 | **Embedding / Rerank** 独立池；**interactive / document / batch / privileged** 队列语义与 PRD 表完全一致 | **ZSET 优先级**（`model:zqueue:*`）、inflight、**Embedding 批** `embedding_batch.py`；Rerank 降级/饥饿等 **仍演进** | [docs/10-model-gateway.md](docs/10-model-gateway.md) |
| §9.3–§9.5 | **指标触发** §9.3 阶梯（P99 60s/120s、队列长度等细分动作）与 **自动恢复**（多指标组合） | **`degradation_auto`** 已用错误率 + 延迟 EMA + good streak；**默认阈值**对齐 §13.1（9.5）；**逐动作映射 rerank/top_k/工具裁剪**仍运维/Prom 规则演进 | `workers/degradation_auto.py`、[`deploy/prometheus/rules/agent_factory.rules.yml`](deploy/prometheus/rules/agent_factory.rules.yml) |
| §9.4–§9.5 | 降级对 **高 `queue_priority` Agent 的资源倾斜**细粒度 | 有队列优先级字段；**与降级联动的公平性策略**可继续打磨 | [docs/13-concurrency.md](docs/13-concurrency.md) |
| §10.2 | **standard / full** 审计档位产品与默认策略 | **以 minimal 为主路径** | [docs/12-security-audit.md](docs/12-security-audit.md) |
| §10.4 | portal-JWT 验签：**JWKS 拉取**公钥（可选表述） | 以当前 exchanged 实现为准；**若 portal 仅 JWKS** 需对齐配置 | [docs/06-api-gateway.md](docs/06-api-gateway.md) |
| §10.6 | **OpenTelemetry** 分布式追踪 | **可选接入**：`OTEL_ENABLED` + `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`；依赖 `uv sync --extra observability`（`infra/otel.py`）；默认关闭 | [docs/32-observability-design.md](docs/32-observability-design.md)、[docs/31-configuration-reference.md](docs/31-configuration-reference.md) |
| §10.6 | **业务层**：DAU/MAU 报表、每日新增对话数、新增 Agent 数、反馈率等 **完备聚合与固定报表** | **轻量接口已提供**：`GET /admin/product-metrics/summary`（[`docs/19-api-reference.md`](docs/19-api-reference.md)）；完备固定报表 / 数仓 / BI 仍分期 | Grafana / 数仓、`services/product_metrics.py` |
| §10.6 | **Agent 层**：每 Agent QPS/错误率/P99/token trend | **`af_frontend_events_total`**（event_type / agent_id）已接线；HTTP QPS 仍依赖 Ingress；完备大盘仍环境绑定 | [`deploy/grafana/dashboards/agent-factory-overview.json`](deploy/grafana/dashboards/agent-factory-overview.json) |
| §10.6 | PRD §10.6 旧句「P0 审计可暂缓」 | **以 [docs/47-prd-alignment.md](docs/47-prd-alignment.md)** 为准（minimal 已写入） | — |
| §10.7 | **HTTPS + HSTS** | **终端 Ingress/网关**配置 | 运维、[docs/41-nginx-config.md](docs/41-nginx-config.md) |
| §10.7 | Widget **禁用第三方 SDK**（GA 等） | **`scripts/check_widget_third_party.py` + CI**；供应链版本锁定仍靠 lockfile 评审 | [`scripts/check_widget_third_party.py`](../scripts/check_widget_third_party.py) |
| §11 §P2–§P3 | 受控脚本、工作流 Skill、**Router Agent**、**multi-skill 再评估** | **运行时代码未交付**；评估见 plan §7–§8 | [docs/50-p2-p3-phase-assessment.md](docs/50-p2-p3-phase-assessment.md) |
| PRD §13.2 | 推荐组合：**pydantic-ai** 内核 + nanobot 借鉴等 | **未引入 `pydantic-ai` 依赖**；自研 Runner 循环 | 可选架构对齐，非功能缺口 |
| §14–§15 | 风险表与评审问题中的 **流程/组织**项（双签、灰度谁批、salt 轮换等） | **流程外置** | 评审工单 |

### 13.3 PRD 章节 → 缺口速查（与 §13.2 同步）

- **§2**：排除项 → 非本仓库 backlog（见 §13.2 首行）。
- **§4–§4.5**：架构图/portal 托管 → 架构示意与门户自有工程；**HSTS** → §13.2 §10.7；**§4.5.5 Agent 列表 RBAC** → §13.2（已回填）。
- **§5–§6**：**脚本运行时** → §13.2 §3.2/P2；`risk.rule_check` **占位 Tool** → §13.1。
- **§7**：**RunSpec v2 / N=2** → §13.2 §7.6；**按需脚本与 hash** → §13.2 §7.7。
- **§8**：**tar.gz/git、静态分析** → §13.2；**评测必选 / Redis 通知** → §13.1；**schema 校验深度** → §13.2 §8（步骤）；**Skill 详情挂载、Registry 写、`kb.search` HTTP** → §13.2（已回填）。
- **§9**：脚本池、Rerank/队列与 **降级矩阵全自动** → §13.2（默认阈值见 §13.1）。
- **§10**：**standard/full 审计**、**OTel（可选已接入）**、**业务报表（轻量 API + 完备报表分期）**、**HSTS** → §13.2；**前端 beacon 指标 / SDK 门禁** → §13.1；**管理台审计 UI** → §13.2 / plan §5（MVP 已部分回填）。
- **§11**：P2/P3 能力 → plan §7–§8；**§11.5** 灰度/版本 → §13.1 已落地部分 + 组织侧「谁批准灰度」→ §13.2。
- **§12**：首批 Agent 样本 → plan §11；PRD 表格中的「价值/风险」属产品运营，不单列代码缺口。
- **§13（PRD）**：技术选型矩阵（pydantic-ai 等）→ §13.2 总表中 **PRD §13.2** 行。

---

**文档版本**：与 docs v0.6（2026-05-06）及 PRD v0.6 对齐；**2026-05-11** 对账更新；**同日代码**：`allowed_agents` 全链路、Registry 写鉴权、`mounted_agents`、`KB_SEARCH_URL`、`/admin/*` 管理台 MVP。若 docs / PRD 更新，请同步调整 §12、§13。
