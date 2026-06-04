# 33. 管理后台设计

> 版本：v0.6 · 2026-05-06

---

## 定位与受众

管理后台（Admin Dashboard）是 Agent App Factory 的**运营控制中心**，面向三类角色：

| 角色 | 职责 | 典型用户 |
|------|------|---------|
| **平台管理员**（platform_admin） | 全局配置、系统运维、安全管理、跨部门协调 | 平台运维团队、安全合规团队 |
| **部门管理员**（department_admin） | 本部门 Agent 生命周期、用户权限、预算分配 | 各业务部门 IT 负责人 |
| **审计员**（auditor） | 只读查询审计日志、生成合规报表 | 内控/审计部门 |

**部署形态**：独立子站（`https://agent.company.com/admin`），与 Chat Widget 分离，走独立的 admin JWT 认证体系。

---

## 功能模块总览

```
┌─────────────────────────────────────────────────────────────┐
│  顶栏：当前角色 + 部门筛选器（平台管理员可见全部）              │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                  │
│  导航栏   │              内容区（按模块切换）                  │
│          │                                                  │
│  · Agent  │                                                  │
│    管理   │                                                  │
│  · Skill  │                                                  │
│    管理   │                                                  │
│  · 用户   │                                                  │
│    权限   │                                                  │
│  · Token  │                                                  │
│    预算   │                                                  │
│  · 审计   │                                                  │
│    查询   │                                                  │
│  · 系统   │                                                  │
│    配置   │                                                  │
│  · 降级   │                                                  │
│    控制   │                                                  │
│          │                                                  │
└──────────┴──────────────────────────────────────────────────┘
```

---

## 模块详细设计

### 1. Agent 管理

**面向**：部门管理员（本部门 Agent）、平台管理员（全部 Agent）

**功能清单**：

| 功能 | 权限要求 | 接口 |
|------|---------|------|
| Agent 列表（按部门过滤） | department_admin+ | `GET /agents` |
| Agent 详情 / 版本历史 | department_admin+ | `GET /agents/{id}` / `GET /agents/{id}/versions` |
| 新建 Agent | department_admin+ | `POST /agents` |
| 编辑 Agent 配置 | department_admin+（本部门） | `PUT /agents/{id}` |
| 发布 / 灰度控制 | department_admin+ | `POST /agents/{id}/releases` |
| 强制下架（紧急屏蔽） | platform_admin | `POST /admin/agents/{id}/disable` |
| 生命周期状态流转 | platform_admin | `PUT /agents/{id}`（修改 lifecycle_state） |
| MAU 体检结果查看 | department_admin+ | 读取 `agent_apps` 表 + `agent_usage_logs` |

**关键交互**：
- **灰度发布面板**：可视化滑动条控制 `percent`，下拉框选择 `target_departments`，实时显示当前灰度用户占比
- **版本对比**：选中两个版本并排对比 `diff`（instruction、tools、limits 等字段高亮变更）
- **生命周期图谱**：active → cold → archived 的流转时间轴，标注触发原因

---

### 2. Skill 管理

**面向**：平台管理员（Skill 注册/下架）、部门管理员（查看本部门可用 Skill）

**功能清单**：

| 功能 | 权限要求 | 接口 |
|------|---------|------|
| Skill 列表 | user+（只读） | `GET /skills` |
| Skill 详情（含版本、挂载 Agent） | user+（只读） | `GET /skills/{id}` |
| 注册新 Skill | platform_admin（双签审批） | `POST /skills` |
| 升级 Skill 版本 | platform_admin（双签审批） | `PUT /skills/{id}` |
| 下架 Skill | platform_admin | `DELETE /skills/{id}`（标记 deprecated） |
| 评测集运行 | platform_admin | 调用 `evals/` 目录下评测脚本（CI 触发） |

**双签审批流程**（见 [16-risk-mitigation.md](16-risk-mitigation.md) §Skill/Tool 新增审批）：
1. 平台管理员 A 提交 Skill 注册申请
2. 平台管理员 B（安全负责人）审批通过
3. 系统自动入库并通知申请人

---

### 3. 用户权限管理

**面向**：平台管理员

**功能清单**：

| 功能 | 权限要求 | 接口 |
|------|---------|------|
| 用户列表 / 搜索 | platform_admin | `GET /admin/users` |
| 用户角色分配 | platform_admin | `PUT /admin/users/{id}/roles` |
| 部门架构管理 | platform_admin | `GET /admin/departments` / `POST /admin/departments` |
| 权限审计：谁访问过哪个 Agent | platform_admin | 查询 `audit_logs` 表聚合 |

**角色与权限映射**（详见 [12-security-audit.md](12-security-audit.md) §RBAC）：

```
platform_admin
  ├── agent.admin（管理所有 Agent）
  ├── skill.publish（注册/升级 Skill）
  ├── tool.admin（注册 Tool）
  ├── degradation.control（降级控制）
  └── policy.admin（修改平台/部门策略）

department_admin
  ├── agent.admin（仅本部门 Agent）
  └── policy.admin（仅本部门策略）

auditor
  └── audit.read（只读查询所有审计日志）

agent.user
  └── 使用已授权的 Agent
```

---

### 4. Token 预算管理

**面向**：平台管理员（全局预算）、部门管理员（本部门预算）

**功能清单**：

| 功能 | 权限要求 | 接口 |
|------|---------|------|
| 各层级预算总览 | department_admin+ | `GET /admin/token-quotas` |
| 调整预算 | department_admin+（本部门及子部门） | `PUT /admin/token-quotas/{scope}/{scope_id}` |
| 预算超限预警配置 | platform_admin | 修改 `system_config` 表 |

**预算面板设计**：
- 仪表盘展示 platform / department / agent / user 四级预算树
- 每个节点显示 `used / budget` 进度条，超 80% 黄色、超 100% 红色
- 点击部门节点下钻，查看该部门下各 Agent 的消耗排名

---

### 5. 审计查询

**面向**：审计员（只读）、平台管理员

**功能清单**：

| 功能 | 权限要求 | 数据来源 |
|------|---------|---------|
| 按条件筛选审计日志 | auditor+ | `audit_logs` 表 + `archives/`（温存储） |
| 单条会话完整轨迹 | auditor+ | `audit_logs` + `checkpoints` 表 |
| 导出审计报表（CSV/Excel） | auditor+ | 聚合查询后生成 |
| 数据保留期配置 | platform_admin | `system_config` 表 |

**查询条件**：
- 时间范围（精确到秒）
- agent_id / user_id_hash（模糊匹配）
- department
- tool_id（调用了哪个工具）
- error_code（是否包含错误）
- level（minimal / standard / full）

**注意**：审计日志查询可能涉及温存储（已归档到 MinIO），超过 90 天的查询耗时较长，UI 应显示进度条和预估时间。

---

### 6. 系统配置

**面向**：平台管理员

**可配置项**（对应 [31-configuration-reference.md](31-configuration-reference.md)）：

| 配置项 | 热加载 | 修改方式 |
|--------|--------|---------|
| `runspec_schema_version_current` | 是（缓存 TTL 1min） | 下拉框选择 |
| `degradation.default_level` | 是（Redis 实时） | 数字输入 0~6 |
| `audit.default_level` | 是（缓存 TTL 5min） | 下拉框 minimal/standard/full |
| `audit.default_retain_days` | 否（下次生效） | 数字输入 |
| `session.default_timeout_minutes` | 是 | 数字输入 |
| `mau.threshold.default` | 是 | 数字输入 |
| `agent.max_versions_keep` | 否 | 数字输入 |
| `skill.max_versions_keep` | 否 | 数字输入 |

**配置变更审计**：所有 `system_config`、`platform_policies`、`org_policies` 的修改记录写入 `config_change_logs` 表（谁、何时、旧值、新值、原因）。

---

### 7. 降级控制

**面向**：平台管理员

**功能清单**：

| 功能 | 权限要求 | 接口 |
|------|---------|------|
| 查看当前降级级别 | platform_admin | `GET /admin/degradation/level`（隐含） |
| 手动启用降级 | platform_admin | `POST /admin/degradation/level` |
| 手动恢复 | platform_admin | `POST /admin/degradation/recover` |
| 查看降级历史 | platform_admin | 查询 `degradation_events` 表 |

**降级面板设计**：
- 大型指示灯显示当前级别（0=绿色，1-2=黄色，3-4=橙色，5-6=红色）
- 触发原因标签：manual / auto_cpu / auto_memory / auto_model / auto_error_rate
- 各级别对应的限制说明卡片（见 [13-concurrency.md](13-concurrency.md) §6 级降级定义）

---

## 前端技术建议

管理后台与 Chat Widget **共享底层技术栈**，但独立构建：

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 框架 | React 18 + TypeScript | 与 Widget 一致 |
| UI 组件库 | Ant Design / Arco Design | 后台场景表格/表单/图表丰富 |
| 状态管理 | Zustand | 与 Widget 一致 |
| 图表 | ECharts / AntV G2Plot | 预算趋势、MAU 曲线、延迟分布 |
| 路由 | React Router | 多模块页面级路由 |
| 构建 | Vite | 与 Widget 一致 |

**独立部署理由**：
- 管理后台用户量极小（几十人），与 Widget（全公司用户）的并发模型完全不同
- 管理后台需要更重的图表和数据表格，bundle 较大，不应拖累 Widget 加载速度
- 安全域隔离：管理后台可走更严格的网络策略（如仅办公网 VPN 可访问）

---

## 权限校验原则

1. **前端路由守卫**：根据当前 admin JWT 中的 `roles` 字段动态渲染导航菜单，无权限的模块不显示（防好奇点击）
2. **后端二次校验**：所有 admin API 必须校验 `Authorization: Bearer <admin-JWT>`，不信任前端传来的任何权限标识
3. **数据域隔离**：department_admin 的查询自动附加 `WHERE department = ?` 条件，平台管理员可传 `department=*` 查看全部
4. **操作审计**：所有写操作（POST/PUT/DELETE）记录操作日志：操作人、时间、对象、变更前后值

---

## Admin JWT 认证序列

管理后台使用独立的 admin JWT 体系（与 Chat Widget 的 session cookie 体系分离）：

```
用户访问 https://agent.company.com/admin
  ↓
1. 检查 localStorage 中是否有有效的 admin JWT
   ├─ 有 → 验证签名和过期时间
   │       ├─ 有效 → 进入管理后台
   │       └─ 过期 → 跳转登录页
   └─ 无 → 跳转登录页

登录页
  ↓
2. 用户输入用户名/密码（或企业 SSO 扫码）
  ↓
3. POST /admin/auth/login
   Body: { username, password, mfa_code? }
  ↓
4. 后端校验：
   ├─ 用户名/密码正确？
   ├─ 用户角色是否包含 platform_admin / department_admin / auditor？
   ├─ MFA 是否通过（如启用）
   └─ 账户是否被锁定？
  ↓
5. 签发 admin JWT：
   {
     "sub": "user_id",
     "roles": ["platform_admin"],
     "department": "*",
     "iat": 1744000000,
     "exp": 1744003600,        // 1 小时过期
     "jti": "admin_jti_001"    // 一次性使用标记（登出时加入黑名单）
   }
  ↓
6. 前端存储 admin JWT 到 localStorage（标记 httpOnly=false，因为纯前端应用需要读取）
   // 注意：虽然存 localStorage 有 XSS 风险，但管理后台使用严格 CSP 缓解
  ↓
7. 后续 API 调用：
   Authorization: Bearer <admin-JWT>
  ↓
8. 后端校验 admin JWT：
   ├─ 签名有效
   ├─ 未过期
   ├─ jti 不在黑名单（Redis `jwt:admin:jti:{jti}`）
   └─ 用户角色允许访问该 API
```

**安全加固**：

| 措施 | 说明 |
|------|------|
| 短有效期 | admin JWT 1 小时过期，减少泄漏窗口 |
| 黑名单登出 | 用户主动登出时 jti 写入 Redis TTL=1h，该 token 立即失效 |
| 操作审计 | 所有 admin API 写操作记录到 `admin_audit_logs` 表 |
| MFA 强制 | platform_admin 必须开启 TOTP；department_admin 可选 |
| IP 白名单 | admin 后台仅允许办公网 / VPN IP 访问（Nginx 层限制） |
| 会话数量限制 | 同一 admin 用户最多 3 个同时登录，超出则踢掉最早的 |

---

## 与现有文档的衔接

- **Admin API 完整定义** → [19-api-reference.md](19-api-reference.md) §用户与权限管理接口、§Token 预算管理接口、§降级运维接口
- **RBAC 详细规则** → [12-security-audit.md](12-security-audit.md) §RBAC
- **降级策略详情** → [13-concurrency.md](13-concurrency.md)
- **审计表结构** → [17-data-models.md](17-data-models.md)
- **配置项清单** → [31-configuration-reference.md](31-configuration-reference.md)
- **双签审批流程** → [16-risk-mitigation.md](16-risk-mitigation.md)
