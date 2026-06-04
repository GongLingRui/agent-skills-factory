# 02. 总体架构设计

> 版本：v0.6 · 2026-05-06

---

## 总体架构图

```
┌─────────────────────────────┐
│         用户 / 业务系统        │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│      API 网关 / SSO / RBAC    │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│      Agent App 注册中心        │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│     Skill Compiler 装配车间    │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│        RunSpec 出厂订单        │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│       共享 Agent Runner      │
└──────┬───────────────┬──────┘
       ↓               ↓
┌────────────┐  ┌──────────────┐  ┌────────────────┐
│ 模型网关 /  │  │ Tool Gateway │→ │ 知识服务（外部）│
│   队列      │  │    安检门     │  │ 文档 / OCR     │
└────────────┘  └──────┬───────┘  │ 内部 API       │
       ↓               │          │ 受控脚本 Worker │
┌──────────────┐       └──────────┴────────────────┘
│  审计 / 日志  │
│ (P0 minimal) │
└──────────────┘
```

---

## 模块职责一句话表

| 模块 | 一句话职责 | 类比 |
|------|-----------|------|
| API 网关 | 认证、识别部门、入口限流 | 公司大门保安 |
| Agent App 注册中心 | 管 Agent 配置、版本、启停、权限 | 岗位说明书档案室 |
| Skill Compiler | 把 Agent + Skill + 权限 + 工具策略**编译**成 RunSpec | 装配车间 |
| Agent Runner | 执行工具调用循环和轻量编排 | 流水线工人 |
| Tool Gateway | 工具注册、权限校验、审计、超时、熔断 | 楼里每个工具室门口的安检门 |
| 模型网关 / 队列 | 模型路由、限流、fallback、token 预算 | 调度中心 |
| 知识服务（外部） | 向量检索、关键词检索、rerank、数据域过滤 | 外协的资料室 |
| 受控脚本 Worker 池 | 跑受控脚本，不按用户起容器 | 共享的临时实验室 |
| 审计 / 日志 | 工具轨迹、输入输出、成本、错误、复现信息 | 监控录像 |

---

## 数据流向

### 正常请求流（一次完整对话）

```
1. 用户在 portal 点击 Agent
   ↓
2. API 网关：JWT 验签 → 识别部门 → 基础限流
   ↓
3. Agent App 注册中心：加载 agent.yaml（按版本/灰度策略）
   ↓
4. Skill Compiler：加载 Skill Package → 权限交集 → 编译 RunSpec
   ↓
5. Agent Runner：按 RunSpec 跑工具调用循环
   ├─→ 需要模型 → 模型网关（队列 → 路由 → fallback）
   ├─→ 需要工具 → Tool Gateway（安检 → 执行 → 返回）
   │       ├─→ kb.search → 知识服务（外部 RAG）
   │       ├─→ doc.extract → 文档解析 Worker
   │       └─→ 内部 API → 内部系统
   ↓
6. 输出按 schema 校验
   ↓
7. 审计记录（minimal 级）
   ↓
8. SSE 流式返回给 widget
```

### 多轮对话流

```
用户打开 Agent → 编译 RunSpec（一次）
   ↓
第 1 轮：用户输入 → Runner 执行 → 模型回复
   ↓
第 2 轮：用户追问 → Runner 在**同一份 RunSpec** 下继续
   ↓
第 N 轮：...
   ↓
max_turns 触发 / 用户开新会话 → **新 RunSpec**
```

**关键**：一次会话 = 一份 RunSpec。多轮对话只是这份 RunSpec 的多次执行，不是每次重新编译。

---

## 模块间接口概览

| 调用方 | 被调用方 | 接口形式 | 关键数据 |
|--------|---------|---------|---------|
| API 网关 | Agent App 注册中心 | 内部函数调用 | agent_id, user_id, department |
| Agent App 注册中心 | Skill Compiler | 内部函数调用 | agent.yaml + Skill Package |
| Skill Compiler | Skill Registry | 读接口 | skill_id, version |
| Skill Compiler | Tool Registry | 读接口 | tool_id, permission |
| Agent Runner | 模型网关 | 异步调用（队列） | prompt, model, max_tokens |
| Agent Runner | Tool Gateway | 同步调用 | tool_id, params, RunSpec |
| Tool Gateway | 知识服务 | HTTP API | query, scopes, top_k |
| Tool Gateway | 文档解析 Worker | 任务队列 | file_url, format |
| Tool Gateway | 受控脚本 Worker | 任务队列 | script_id, input, timeout |
| 所有模块 | 审计模块 | 异步日志 | run_id, trace |

---

## 与外部系统边界

```
┌─────────────────────────────────────────┐
│           Agent App Factory             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │  本系统  │  │  本系统  │  │  本系统  │ │
│  └────┬────┘  └────┬────┘  └────┬────┘ │
│       │            │            │      │
│  ┌────┴────────────┴────────────┴────┐ │
│  │           Tool Gateway             │ │
│  └────┬────────────┬────────────┬────┘ │
└───────┼────────────┼────────────┼──────┘
        │            │            │
   ┌────┘            │            └────┐
   ↓                 ↓                 ↓
┌────────┐    ┌────────────┐    ┌──────────┐
│ 知识服务 │    │  内部 API   │    │ 模型网关  │
│(RAG系统) │    │ (OA/ERP等) │    │(国产模型) │
└────────┘    └────────────┘    └──────────┘
   ↑                 ↑                 ↑
   └────── 外部系统 ──┴────── 外部系统 ──┘
```

**本系统不实现的（通过 Tool Gateway 调用）**：

- 向量检索、全文检索、rerank → 知识服务
- 文档解析 / OCR → 文档解析服务
- 内部制度 / 合同模板查询 → 内部 API
- 模型推理 → 模型网关（国产模型 / OpenAI 兼容网关）

**本系统消费的（通过 Skill Registry 拉取）**：

- Skill Package → Skill Creator 系统产出

---

## 无状态 vs 有状态

| 模块 | 状态属性 | 说明 |
|------|---------|------|
| API 网关 | 无状态 | 纯认证 + 路由 + 限流 |
| Agent App 注册中心 | 有状态（缓存） | agent.yaml 版本数据常驻内存 |
| Skill Compiler | 无状态 | 编译是纯函数，输入确定输出确定 |
| Agent Runner | 有状态（会话级） | 每份 RunSpec 绑定一个会话 |
| 模型网关 | 有状态（队列） | LLM 请求队列、token 预算 |
| Tool Gateway | 无状态 | 每次调用独立校验 |
| 审计 / 日志 | 有状态（存储） | 持久化审计记录 |
| Chat Widget | 有状态（前端） | localStorage + IndexedDB |

## 分布式数据一致性策略

本系统涉及 PostgreSQL、Redis、MinIO 三个存储层，以下策略保证最终一致性：

### 1. 写穿透 + 消息通知（Write-Through + Pub/Sub）

Agent / Skill / Policy 更新时的标准流程：

```
管理后台 PUT /agents/{id}
  ↓
1. 写 PostgreSQL 主库（事务内完成）
  ↓
2. 写 Redis（SETEX 更新缓存）
  ↓
3. 发布 Redis Pub/Sub（agent:updated）
  ↓
4. 其他实例订阅 channel，清除本地 Caffeine/LRU 缓存
```

**异常处理**：
- PG 写入成功但 Redis 写入失败 → 下次读请求回源 PG 刷新 Redis，自愈
- Redis 写入成功但 Pub/Sub 失败 → 本地缓存 TTL 到期后自动回源，最长 5 分钟不一致

### 2. Skill 包上传的两阶段提交

Skill 包同时写入 DB 和 MinIO：

```
Skill Creator 上传 tar.gz
  ↓
1. 上传 MinIO（返回 storage_path）
  ↓
2. 若 MinIO 成功 → 写入 PostgreSQL skills 表
  ↓
3. 若 PG 失败 → 删除 MinIO 对象（补偿操作）
  ↓
4. 若 PG 成功 → 发布 skill:updated
```

**为什么先 MinIO 后 PG**：MinIO 写失败概率低于 PG（无事务竞争），先写 MinIO 减少补偿操作频率。

### 3. 文件上传端到端一致性

```
用户上传文件
  ↓
1. 后端接收 → 直传 MinIO temp/ 桶（返回 storage_path）
  ↓
2. 写入 PostgreSQL file_uploads 表（状态=pending）
  ↓
3. 投递 doc_worker 队列
  ↓
4. Doc Worker 解析完成 → 写 MinIO temp/（extracted_text_path）
  ↓
5. 更新 PostgreSQL file_uploads 状态=extracted
```

**不一致处理**：
- MinIO 有文件但 PG 无记录 → cron 任务扫描 MinIO temp/，清理 orphan 对象（24h 后）
- PG 有记录但 MinIO 文件丢失 → doc.extract 调用时返回 `FILE_NOT_FOUND`，模型自行处理

### 4. 会话过期一致性

```
sessions.expires_at（PG 权威来源）
  ↓ 同步
Redis session:{id} TTL
  ↓ 同步
浏览器 cookie max-age
```

**权威来源**：以 PostgreSQL `sessions.expires_at` 为准。Redis TTL 和 cookie max-age 与之同步，但服务端最终校验以数据库为准。

---

## 缓存失效机制

### 缓存分层

| 数据 | 缓存位置 | TTL | 失效触发源 |
|------|---------|-----|-----------|
| agent.yaml | 本地内存 + Redis | 5 分钟 | Agent 更新 / 版本发布 |
| Skill Package 元数据 | Redis | 10 分钟 | Skill Registry 升级 |
| platform_policy / org_policy | Redis | 1 分钟 | 策略管理后台修改 |
| 用户权限列表 | Redis | 5 分钟 | RBAC 系统变更 |
| 模型可用性状态 | Redis | 10 秒 | 健康检查探针 |

### Skill 升级时的级联失效

当 Skill Creator 上传新版本（如 clause-review v0.1.0 → v0.1.1）时：

```
Skill Registry 写入新版本
  ↓
发布 Redis Pub/Sub 消息：channel = "skill:updated", payload = { skill_id, version }
  ↓
所有 Core 服务实例订阅该 channel
  ↓
各实例：
  - 清除本地 Skill Package 缓存
  - 清除 Redis 中该 Skill 的元数据缓存
  - 清除所有挂载该 Skill 的 Agent 的 agent.yaml 缓存（因为 allowed_tools / knowledge_scopes 可能变化）
  - 已运行的会话不受影响（RunSpec 已钉死版本）
```

**关键**：不主动通知每个客户端（widget），因为 RunSpec 不可变，新会话才会拉取新版。

### Agent 配置更新时的失效

业务部门修改 agent.yaml（如改 ui_config 欢迎语）：

```
管理后台 PUT /api/v1/agents/{agent_id}
  ↓
数据库写入新版本，旧版本保留
  ↓
发布 Redis Pub/Sub：channel = "agent:updated", payload = { agent_id, version }
  ↓
Core 服务清除该 Agent 的本地缓存
  ↓
新会话编译时自动拉取最新版
```

### 缓存失效的兜底

- 每个缓存 key 带 **逻辑版本号**（如 `agent:contract-review-agent:v3`），写入时递增
- 读缓存时校验版本号与数据库最新版是否一致，不一致则回源刷新
- 避免 "缓存雪崩"：热点 Agent 的缓存失效后，使用互斥锁（Redis SETNX）保证只有一个实例回源

---

## 部署拓扑（建议）

```
┌─────────────────────────────────────────┐
│              Nginx / LB                  │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│         API Gateway (3 实例)             │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│      Agent App Factory Core (3 实例)     │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐  │
│  │ 注册中心 │ │Compiler │ │ Runner   │  │
│  └─────────┘ └─────────┘ └──────────┘  │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│          Redis（缓存 + 队列）             │
│          PostgreSQL（持久化）             │
│          MinIO / S3（Skill 包存储）       │
└─────────────────────────────────────────┘
```

- 所有核心服务实例共享 Redis + PostgreSQL
- Skill Package 存对象存储，运行时再拉
- 文档解析和脚本 Worker 独立部署，通过队列消费任务

---

## 架构评审问题与决策记录

本节记录 PRD 评审阶段的关键问题及当前方案的决策，供后续架构演进时参考。

| 序号 | 评审问题 | 决策结论 | 相关文档 |
|------|---------|---------|---------|
| 1 | Agent App 是否比通用动态 Skill Router 更适合企业内网？ | **是**。动态路由在企业内网会把复杂度、安全边界和并发成本拉爆。P0-P2 坚持"一个 Agent 绑定一个 Skill"，P3 再评估 Router Agent | [01-overview.md](01-overview.md), [03-agent-app-spec.md](03-agent-app-spec.md) |
| 2 | Skill 作为能力编译层是否足以支撑大量业务 Agent？ | **是**。声明式配置 + Skill Compiler + RunSpec 的工厂模式，让业务部门不碰代码即可生产 Agent。数量增长时只需增加配置，不增加运行时复杂度 | [07-skill-compiler.md](07-skill-compiler.md) |
| 3 | references/ 的加载策略选 prompt 拼接、检索索引，还是混合？ | **混合**。always（短规则编译时拼）+ on_demand（运行时按需拉）+ indexed（进知识库检索）。由 Skill Creator 在 enterprise.yaml 中声明 load_policy | [04-skill-package-spec.md](04-skill-package-spec.md) |
| 4 | scripts/ 是 P0 就出现，还是先限制为 build-time/eval？ | **P0 仅 build-time**。P0 不开放运行时脚本。scripts/ 只用于校验、生成 schema、跑 eval。P2 才引入受控 Worker 跑预处理脚本 | [04-skill-package-spec.md](04-skill-package-spec.md), [25-script-worker.md](25-script-worker.md) |
| 5 | Tool Gateway 的权限模型够不够硬？ | **4 层校验**：RunSpec 白名单 + 用户 RBAC + 数据域权限 + Gateway 策略（工具下线/熔断）。不依赖 prompt 层约束 | [09-tool-gateway.md](09-tool-gateway.md) |
| 6 | 多并发瓶颈主要会在模型、文档解析、检索，还是脚本 worker？ | **模型层是最大瓶颈**。方案：队列 + token 预算 + fallback + 降级。文档解析和脚本 Worker 拆独立资源池 | [13-concurrency.md](13-concurrency.md), [10-model-gateway.md](10-model-gateway.md) |
| 7 | RunSpec schema_version 字段从第一天就加？ | **是**。v1 从 P0 开始，Runner 向后兼容 N=2 个大版本，保证审计可复现 | [05-runspec.md](05-runspec.md), [03-agent-app-spec.md](03-agent-app-spec.md) |
| 8 | PoC 起点用 pydantic-ai + nanobot 借鉴的组合，还是单基座 fork？ | **组合借鉴，不 fork**。pydantic-ai 做 type-safe 内核 + nanobot 借 SKILL.md 加载器 + 自建企业治理层 + 接口对齐 OpenAI Agents SDK | [15-tech-stack.md](15-tech-stack.md) |
| 9 | Skill Registry 的版本升级走热加载还是冷部署？ | **小版本热加载 + 大版本灰度**。小版本（0.1.0→0.1.1）已运行会话用旧版 RunSpec，新会话用新版；大版本（0.x→1.0）按 agent.yaml skill_version_pin 控制 | [04-skill-package-spec.md](04-skill-package-spec.md) |
| 10 | Tool Registry 的双签审批流程谁来定？ | **平台团队定流程，安全部门评审**。新增 Tool = 扩大攻击面，必须过双签 + 安全评审。业务部门只能提需求，不能自行注册 | [09-tool-gateway.md](09-tool-gateway.md) |
| 11 | MAU 元数据的 user_id_hash salt 怎么管理 / 多久轮换？ | **K8s Secret 管理，每季度轮换**。双 salt 并行 90 天，轮换期间 MAU 统计取保守估算（MAX 法）| [12-security-audit.md](12-security-audit.md) |
| 12 | widget 的 Agent 切换 UX 是顶栏下拉还是侧栏抽屉？ | **顶栏下拉**。类比桌面浏览器标签页，认知成本低；session cookie 不绑 agent_id，支持自由切换 | [11-chat-widget.md](11-chat-widget.md) |
| 13 | Agent 灰度发布的"目标部门"由谁决定？ | **业务部门 owner 提议 + platform_admin 审批**。业务部门知道自己要灰度给谁，但策略执行需平台管理员确认，防止误放量 | [03-agent-app-spec.md](03-agent-app-spec.md), [14-roadmap.md](14-roadmap.md) |
| 14 | 为什么 RunSpec 不变 ≠ 权限永远不变？ | **RunSpec 不变指 prompt 拼装层不变**；但 Tool Gateway 和模型网关每次调用时实时校验权限 / 限流 / 模型降级 / 工具下线，以 RunSpec 上界 ∩ 当前策略为准 | [05-runspec.md](05-runspec.md), [08-agent-runner.md](08-agent-runner.md) |
