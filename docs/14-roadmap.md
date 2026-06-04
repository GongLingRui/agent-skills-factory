# 14. P0 → P3 路线图

> 版本：v0.6 · 2026-05-06

---

## P0：声明式 Agent App + 用户入口

### 后端

- Agent App Manifest
- 静态 Skill Package 绑定（一个 agent 一个 Skill Package，**内部 progressive disclosure**）
- SKILL.md + enterprise.yaml
- references/（双兼容 reference/）
- 输出 schema
- 简单工具调用循环
- 基础知识检索工具
- **最小审计开启**（audit.level: minimal：工具轨迹 + 检索 ID + 错误码，不含 prompt 内容）
- **`/auth/exchange` JWT 短令牌交换接口**

### 前端 / 入口（与后端同步上线）

- **Embeddable Chat Widget MVP**（独立子站、SSE 流式、文件上传、**分层存储**：localStorage 轻偏好 + IndexedDB 对话历史 + 敏感文件不落盘、export/import）
- **portal 集成**（应用启动器按钮 → /auth/exchange → window.open 新 tab）
- agent.yaml ui_config 字段渲染（标题 / 头像 / 欢迎语 / 输入框提示 / 快捷指令 / 文件上传配置）

**P0 不开放运行时脚本。scripts/ 仅用于 build-time 校验和评测。**

---

## P0.5：审计消费端与上线加固（建议紧接 P0，约 1 周）

**与「最小审计」的关系**：**审计写入（minimal 落库）在 P0 已完成**。本阶段交付的是 **审计消费端**（谁来查、怎么导出），以及压测与安全加固——**不是**「从 P0.5 才开始记审计」。

典型交付物：

- 管理台 / 运维视角：**审计明细查询**、按 agent / 用户 / 时间筛选、合规常用字段导出
- **压测**与容量基线、配额与限流参数校准
- **安全加固**（依 [45-security-architecture.md](45-security-architecture.md)、渗透复测项）

可与 **P1** 并行排期（例如 P1 启动后仍并行完成 P0.5 报表末段），但建议在广义「上线窗口」内闭环。

---

## P1：Skill 与工具体系深化

- SKILL.md frontmatter 完整化
- enterprise.yaml 策略与评测闭环
- Skill 声明工具依赖和知识范围（与 Tool Gateway 权限交集联动）
- schema 校验与评测用例体系统一
- **不包含**「首次接入审计写入」——该项已在 P0；审计查询类能力见 **P0.5**

---

## P2：受控脚本

- 受控的预处理 / 后处理脚本
- 脚本 Worker 池
- 脚本 manifest
- 输入输出 schema
- 超时、无网络、临时文件系统
- 脚本审计

---

## P3：工作流 Skill 和 Router Agent

- Skill 声明小型 DAG
- Agent 内部轻量步骤编排
- 可选 Router Agent 选具体 Agent App
- **multi-skill agent 也在这一阶段重新评估**

---

## Agent 版本管理 / 灰度 / 回滚

agent.yaml 升级是高频操作（改 prompt / 改工具 / 改 ui_config）。**版本管理必须从 P0 就有**，否则上线后第一次升级就会出事故。

### 发布策略

| 策略 | 适用场景 | 怎么实现 |
|------|---------|---------|
| **全量发布**（默认） | 改 ui_config 文案、改欢迎语等小改 | 升级后所有新会话用新版，已运行会话用旧版（RunSpec 钉死） |
| **灰度发布** | 改 prompt、改工具、改输出 schema | 按部门或用户百分比放量（先 10% → 50% → 100%） |
| **回滚** | 新版上线后发现 bug | 一键切回上个版本，已用新版的会话不影响（已编译的 RunSpec 不变） |

### 技术实现

- agent.yaml 的 version 字段必填
- Agent App 注册中心保留最近 10 个历史版本
- Skill Compiler 编译时按 traffic split 决定本次会话用哪个版本
- RunSpec 里钉死 agent_version——会话中途不会切版本

### 灰度配置示例

```yaml
# agent.yaml 顶层增加
release:
  strategy: canary          # full / canary / pinned
  canary:
    percent: 10             # 10% 流量用新版
    target_departments:     # 部门级灰度
      - legal
    target_users:           # 用户级白名单（测试账号、业务 owner 提前验证）
      - u_test001
      - u_owner_legal
  pinned_version: 0.0.9     # rollback 时用这个
```

**canary 命中逻辑（满足任一即灰度）**：

```python
is_canary = (
    user_in_target_users(user_id, canary.target_users) or
    user_in_target_departments(department, canary.target_departments) or
    hash(user_id) % 100 < canary.percent
)
```

- 命中逻辑：满足**任一条件**即灰度（`or` 短路求值）
- 评估顺序：`target_users` → `target_departments` → `percent`（短路求值，先命中先返回）
- `target_users`：用于测试账号、业务 owner 提前验证
- `target_departments`：用于部门级灰度
- `percent`：按用户 ID hash 取模，保证同一用户始终命中同一版本

---

## 第一批做哪些 Agent

建议从 3-5 个开始：

| Agent | 价值 | 风险 |
|-------|------|------|
| 制度问答 | 最容易落地，验证知识库权限 | 幻觉和引用准确性 |
| 合同审查 | 高价值，验证文档解析和规则工具 | 法务准确性要求高 |
| 会议纪要 | 高频刚需，验证文本生成 | 格式和保密 |
| 材料起草 | 高频高感知 | 风格一致性 |
| 舆情简报 | 验证多源检索和摘要 | 数据源与时效 |

---

## 里程碑时间表（估算）

| 阶段 | 周期 | 核心交付物 |
|------|------|-----------|
| P0 后端 | 4-6 周 | API 网关、注册中心、Compiler、Runner、Tool Gateway MVP、模型队列、**minimal 审计写入** |
| P0 前端 | 2-3 周（并行） | Chat Widget MVP、portal 集成、分层存储 |
| P0.5 | 约 1 周 | **审计消费端**（查询/报表/导出）、压测、安全加固 |
| P1 | 3-4 周 | Skill 与评测体系深化、工具与 schema 闭环（不含首次审计落库） |
| P2 | 4-6 周 | 受控脚本、Worker 池、脚本审计 |
| P3 | 6-8 周 | 工作流、Router Agent、multi-skill 评估 |
