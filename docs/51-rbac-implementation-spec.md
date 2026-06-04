# 51. 完整 RBAC 立项与实施规格

> 版本：v0.1 · 2026-05-11  
> 关联：[prd.md](../prd.md) §10.1、[12-security-audit.md](12-security-audit.md) §RBAC、[33-admin-dashboard-design.md](33-admin-dashboard-design.md)、[47-prd-alignment.md](47-prd-alignment.md)

---

## 1. 目标与边界

### 1.1 目标

在 **portal 仍为身份源（SSO + JWT）** 的前提下，将本仓库从「少量硬编码权限串」演进为与 `docs/12`、`docs/33` **对齐的权限模型**：

- 能力码（permission codes）可校验、可测试、可文档化。
- 角色名（`platform_admin` / `department_admin` 等）在服务端 **展开** 为能力码集合，避免门户只发粗粒度 token 时无法接管理台。
- **Tool Registry** 工具的 `permission_required` 与 **调用方 JWT 展开后的能力** 求交（与 PRD §10.1「系统层校验」一致）。
- 管理类 HTTP 接口：**运维 Bearer** 与 **会话 RBAC** 并存（兼容自动化与人工运营）。

### 1.2 非目标（仍不在本仓交付）

- 本仓自建用户目录 / 与 portal 双向同步用户主数据（仍以 portal JWT `sub` + claims 为准）。
- `docs/12` 中 Input Sanitizer / `security_events` 全量落地（属安全纵深，见 [12-security-audit.md](12-security-audit.md) 其他章节）。

**阶段 C 已落地（本仓）**：`department_admin` 且非 `platform_admin` 时，注册中心 `AgentApp.owner` 须等于会话 `department`；列表/读写/生命周期/发布均按该规则过滤或拒绝（`agent_apps.owner` 与门户部门编码对齐由集成方保证）。

---

## 2. Portal JWT 契约（建议）

门户在 **exchange** 使用的 JWT 中建议携带：

| Claim | 类型 | 说明 |
|-------|------|------|
| `permissions` | `string[]` | **能力码** 与/或 **角色名**（见 §3）；至少为会话用户真实能力 |
| `allowed_agents` | `string[]` 或省略 | 可选；省略表示不在列表层收紧（与实现对齐） |

能力码常量见实现模块 `agent_factory.core.rbac`（与 `docs/12` 表对齐并扩展 `knowledge.read` 等预留位）。

---

## 3. 角色展开规则（服务端）

当 `permissions` 中含下列 **角色 token** 时，在 `effective_permissions()` 中并入对应能力（实现见 `core/rbac.py`）：

| 角色 token | 展开（摘要） |
|------------|----------------|
| `platform_admin` | `agent.admin`、`agent.write`、`skill.publish`、`tool.admin`、`audit.read`、`degradation.control`、`policy.admin`、`agent.read` |
| `department_admin` | `agent.admin`、`agent.write`、`skill.read`、`policy.admin`、`agent.read`（**不含** `skill.publish` / `tool.admin` 全平台级） |

---

## 4. 兼容策略：`agent.admin` 遗留语义

环境变量 **`RBAC_LEGACY_AGENT_ADMIN_IMPLIES_FULL`**（默认 `true`）：当会话含 `agent.admin` 时，**额外**视为拥有 `skill.publish`、`tool.admin`、`audit.read`、`degradation.control`、`policy.admin`，以免门户尚未拆分细粒度权限时 **生产中断**。

新门户集成应逐步改为显式能力码，并将该开关置为 `false`。

---

## 5. HTTP 路由与所需能力（本仓库）

| 区域 | 路由（示例） | 会话需要（展开后） | 运维 Bearer |
|------|----------------|-------------------|-------------|
| Agent 注册写 | `POST/PUT /agents` | `agent.write` 或 `agent.admin` | `ADMIN_API_TOKEN` |
| Agent 下架/生命周期 | `DELETE /agents`、`PATCH .../lifecycle` | `agent.admin` | 同左 |
| Skill 注册/更新 | `POST/PUT /skills` | `skill.publish`（或由角色/遗留展开） | 同左 |
| Skill 下架 | `DELETE /skills` | `agent.admin`（与 docs/33「平台下架」一致） | 同左 |
| Tool 注册/更新 | `POST/PUT /tools` | `tool.admin` | 同左 |
| 审计只读 | `GET /audit/*` | `audit.read` | `ADMIN_API_TOKEN` |
| 降级控制 | `POST /admin/degradation/*` | `degradation.control` | 同左 |
| 产品指标 | `GET /admin/product-metrics/summary` | `platform_admin` / `department_admin` **或** `agent.admin` / `agent.write` / `audit.read`（运营只读） | 同左 |

---

## 6. Tool Gateway 与 Runner

- `RunnerService.run_turn(..., caller_permissions=...)` 将 **展开后的能力集** 传入 `ToolGateway.validate_and_run_async`。
- 对 **Registry `http_api` 工具**：若 `tools.permission_required` 非空，则要求 **每一项** 均出现在 `caller_permissions` 中；否则 `403`。
- **内置工具**（`kb.search` 等）不读 Registry 行时 **不**套用 `permission_required`（仍以 RunSpec + 数据域为准）。
- `caller_permissions` 为 `None` 时（仅测试/内部调用）**跳过** Registry 工具的能力交校验，避免破坏旧单测；生产路径由 `agents.chat` 始终传入会话展开集。

---

## 7. 实施阶段（与 plan.md 勾选同步）

| 阶段 | 内容 | 状态 |
|------|------|------|
| **A** | `core/rbac.py`、`RBAC_LEGACY_*`、deps 拆分、审计/降级/指标、Skill/Tool 写、Runner→Gateway 传参 | **已落地** |
| **B** | 管理台 UI 按能力隐藏菜单；`GET /auth/me` 返回 `effective_permissions` 摘要供前端 | **已落地**（`AdminLayout` + `effective_permissions` / `can_view_product_metrics`；Bearer 时仍展示全菜单） |
| **C** | 部门资源范围：`department_admin` 仅能操作 `agent_apps.owner` 等于会话 `department` 的资源 | **已落地**（`/api/v1/agents` 注册路由与 `GET/PATCH /api/v1/admin/agents`） |
| **D** | 权限缓存 TTL（`docs/12` 5 分钟）与 portal 撤销联动 | **已落地**：`RBAC_PERMISSION_CACHE_SECONDS` 在 `GET /auth/me` 的 `rbac.permission_cache_seconds` 披露；`POST /auth/sync-permissions` 用门户 Bearer 刷新会话权限；`POST /admin/session-revocations`（`ADMIN_API_TOKEN`）递增撤销世代；`sessions.permissions` / `revoke_gen_seen` 持久化 |

---

## 8. 验收建议

- 单元测试：`tests/unit/test_rbac.py`（角色展开、遗留开关、交集逻辑、**部门注册中心 scope**）。
- 集成测试：会话仅含 `audit.read` 可调 `GET /audit/logs`；不含则 403；Bearer 仍可用；`POST /admin/session-revocations` 需运维 Bearer。
- 门户联调清单：`permissions` 最小集 / 角色-only / 细粒度-only 三套 JWT；**撤销**后同会话 `resolve` 应 `401 SESSION_REVOKED`；权限变更后可调 **`POST /auth/sync-permissions`**（Cookie + 门户 Bearer）。

---

## 9. 本阶段新增 HTTP 契约（摘要）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/auth/sync-permissions` | HttpOnly 会话 Cookie + `Authorization: Bearer` 门户 JWT；刷新 `sessions.permissions` 与 Redis 会话缓存 |
| `POST` | `/api/v1/admin/session-revocations` | `Authorization: Bearer <ADMIN_API_TOKEN>`；body `{"user_id_hash":"..."}`，递增该用户的撤销世代 |
| `GET` | `/api/v1/auth/me` | 增加 `can_view_product_metrics`、`rbac.permission_cache_seconds` |
