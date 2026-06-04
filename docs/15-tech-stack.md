# 15. 技术选型

> 版本：v0.6 · 2026-05-06

---

## 自建什么 / 复用什么

不建议找一个重产品大改，更建议**自建薄层 + 按需复用底层组件**。

### 选型标准

- 是否支持 OpenAI 兼容模型
- 是否能嵌进现有后端
- 是否能控制工具执行
- 是否能接企业 RBAC 和审计
- 是否不强迫用它的产品形态
- 是否轻量、可替换

### 自建部分

- Agent App 注册中心
- Skill Compiler
- RunSpec
- Tool Gateway
- 模型队列
- 审计
- **Embeddable Chat Widget**（前端独立子站）
- **`/auth/exchange` 接口**（portal SSO 集成）

### 可复用部分

- 向量库、全文检索、reranker
- 文档解析 / OCR
- OpenAI 兼容客户端
- 轻量工具调用循环
- 任务队列和 worker 框架

---

## PoC 起点的多源参考矩阵

**重要：不 fork 任何一个项目当底座**。从每个项目里挑一块借鉴：

| 项目 | 语言 | 借鉴什么 | 不要的部分 | 活跃度 |
|------|------|---------|-----------|--------|
| **HKUDS/nanobot** | Python | SKILL.md 加载器、summary-first progressive disclosure、AgentRunSpec 抽象、ToolRegistry 薄层 | chat 渠道、公开 Skill 安装、个人 memory、本地 shell | 0.1.x，活跃迭代 |
| **pydantic-ai** | Python | **类型安全的工具注册 + 输出 schema 强制校验**——本方案 §6 输出校验的工业级参考 | 没企业治理层，要自己加 | 高活跃，已用于生产 |
| **OpenAI Agents SDK** | Python/TS | 工具调用、handoffs、tracing 三个抽象的工业接口形状（即使不用 OpenAI 模型也建议接口对齐） | 强绑 OpenAI 调用栈，国产模型适配要改 | 工业事实标准 |
| **HuggingFace smolagents** | Python | code-centric agent 模式——P2 做受控脚本时回来看 | 默认任意代码执行，P0/P1 不要碰 | 高活跃 |
| **Agno** | Python | minimal agent kernel + 多模态接入。如果 nanobot 0.1.x 太不稳定，Agno 是替代候选 | 生态较新，企业 reference 不多 | 中等，社区起势 |
| **Letta（前 MemGPT）** | Python | **反向参考**：它的 server-side stateful memory + REST API 是我们**不要**的（我们选 localStorage）。但它的 memory schema 设计可借鉴到本地存储数据结构 | server-side 整套不要 | 高活跃 |

### 推荐组合

> **P0 PoC = pydantic-ai 做 type-safe agent loop 内核 + nanobot 借 SKILL.md 加载器 + 自建 RunSpec / Tool Gateway / 模型队列 + 接口形状对齐 OpenAI Agents SDK**

好处：pydantic-ai 工业可靠 + nanobot 的 Skill 标准 + 自建企业治理 + 接口标准化。

**不要单 fork**——任何一个项目你 fork 都要扛它的命运（社区 drift / 维护停滞 / 风格漂移）。

---

## nanobot 的具体借鉴清单

### 保留借鉴

- AgentRunSpec / AgentRunner 的分离方式
- SkillsLoader 对 SKILL.md frontmatter 和 summary-first 加载的处理
- ToolRegistry 的工具 schema、参数校验和执行封装
- session lock、pending queue、mid-turn injection 的并发处理思路
- checkpoint、tool result budget、history snip、microcompact 等上下文治理细节
- MCP 工具接入方式

### 替换或裁剪

- 把 chat 渠道替换为企业 API 网关 / Web UI / 内部系统入口
- 把 workspace-level skills 替换为 Agent App 静态绑定 skills
- 把公开 ClawHub Skill 安装替换为内部 Skill Registry、审批和版本管理
- 把本地 exec/file 工具替换为企业 Tool Gateway 受控工具
- 把个人 memory 改为前端 localStorage（按 §10.3）
- 把本地 workspace 沙箱替换为受控 Worker 池

---

## Chat Widget 技术栈推荐

### 推荐栈

- **React 18 + TypeScript**——生态最厚、央企招聘容易、长期可维护
- **shadcn/ui**——轻量组件库，可复制粘贴改样式，不绑死任何设计系统
- **TailwindCSS**——样式即类名，UI 改动快
- **EventSource (SSE)**——流式输出标准方案，比 WebSocket 简单
- **Zustand**——轻量状态管理（聊天历史 / 当前会话 / 上传文件）
- **Vite**——构建工具，启动快
- **dexie.js**（**必备**，按 §10.3 分层存储要求）——IndexedDB 包装，存对话历史 + TTL + 可选加密

### 央企 UI 一致性替代

如果央企对 UI 一致性有强要求：

- 把 shadcn/ui 替换为 **Ant Design** 或 **Arco Design**——后者是字节系的设计语言，央企接受度高、组件齐全
- TailwindCSS 仍可保留处理细节样式

### 不推荐

- Vue + 自研组件——长期维护负债重
- Next.js / Remix——SSR 框架对 SSO + iframe 场景没必要的复杂度
- jQuery / 模板渲染——不要走回头路

---

## Chat Widget MVP 工程量估算

一个全职前端开发者的排期参考：

| 模块 | 工作量 | 说明 |
|------|--------|------|
| widget 框架搭建（路由 / SSO 验签 / session 管理） | 3 天 | 含 token 交换、cookie 管理、心跳保活 |
| 聊天界面（消息流 / SSE 流式 / 输入框 / 快捷指令） | 3 天 | 含 markdown 渲染、代码块高亮、流式打字机效果 |
| 文件上传 + 进度提示 | 1 天 | 含前端预检、拖拽上传、上传进度条 |
| 分层存储（localStorage 轻偏好 + IndexedDB 历史 + 导出导入） | 2 天 | 含 dexie.js 集成、TTL 清理、JSON 导出导入 |
| ui_config 字段动态渲染 | 1 天 | 顶栏 / 欢迎语 / 头像 / 快捷指令按钮的动态切换 |
| Agent 切换（顶栏下拉 + 最近列表 + 收藏） | 1 天 | 含 localStorage 最近列表维护、切换时上下文重建 |
| 联调 + bug 修复 | 2 天 | 与后端接口联调、边界 case 处理 |
| **MVP 总计** | **约 13 个工作日（2.5 周）** | 与后端 P0 并行，不抢人 |

---

## 后端技术栈建议

| 层次 | 技术 | 说明 |
|------|------|------|
| 编程语言 | Python 3.11+ | pydantic-ai、nanobot 都是 Python |
| Web 框架 | FastAPI | 异步、自动文档、OpenAPI 规范 |
| 数据库 | PostgreSQL 15+ | Agent / Skill / Tool 元数据持久化 |
| 缓存 | Redis 7+ | 会话缓存、限流计数、队列 |
| 对象存储 | MinIO | Skill Package 存储 |
| 消息队列 | Redis Stream / RabbitMQ | 异步任务、脚本 Worker |
| 观测性 | Prometheus + Grafana | metrics + 告警 |
| 日志 | Loki + Grafana | 日志聚合 |
| 容器 | Docker + K8s（可选） | 企业内网可能用物理机 / VM |

---

## OpenAI Agents SDK 接口对齐映射表

本系统不依赖 OpenAI 调用栈，但核心接口形状与 OpenAI Agents SDK 对齐，降低开发者学习成本和迁移成本。

| OpenAI Agents SDK 概念 | 本系统对应概念 | 差异说明 |
|------------------------|---------------|---------|
| `Agent` | `Agent App`（由 agent.yaml + Skill 定义） | 本系统 Agent 是静态配置的 App，非运行时动态创建 |
| `handoff` | **P0 不支持**（P3 评估 Router Agent） | 动态路由在企业内网复杂度过高 |
| `function_tool` | `Tool Gateway` 注册的工具 | 本系统增加 4 层权限校验 + 审计 + 熔断 |
| `RunContext` | `RunSpec` | RunSpec 是不变的编译产物，含完整执行上下文 |
| `Runner.run()` | `Agent Runner` 执行循环 | 本系统增加 checkpoint、tool result budget、history snip |
| `TResponseFormat` | `output_schema` + JSON Schema 校验 | 本系统支持 schema 校验失败时的 fallback 策略 |
| `guardrail` | `platform_policy` + `org_policy` + Tool Gateway 策略 | 本系统策略层更厚重，覆盖企业合规要求 |
| `tracing` | `audit`（minimal/standard/full） | 本系统审计分三档，默认 minimal |
| `tool_choice` | `allowed_tools`（RunSpec 白名单） | 本系统由 Skill Compiler 在编译期收敛权限 |

### 接口形状参考

**OpenAI Agents SDK 风格（本系统接口设计参考）**：

```python
# OpenAI Agents SDK 风格（参考）
from agents import Agent, Runner
agent = Agent(name="contract-review", instructions="...")
result = Runner.run(agent, input="审查这份合同")

# 本系统实际调用风格（对齐但增加企业治理层）
from agent_factory import SkillCompiler, AgentRunner
run_spec = SkillCompiler.compile(agent_id="contract-review-agent", user_id="u123")
result = AgentRunner.run(run_spec, user_message="审查这份合同")
```

**对齐原则**：概念名称一致、参数语义一致、错误码风格一致。实现层替换为自建企业治理 + 国产模型适配。

---

## 模型层建议

| 模型 | 用途 | 备注 |
|------|------|------|
| Qwen3-32B | 默认主力模型 | 国产、内网可部署、OpenAI 兼容 |
| Qwen3-14B | fallback | 容量不足时降级 |
| Qwen3-8B | low_cost | 高峰期降级 |
| BGE-M3 | Embedding | 向量检索 |
| 内部 reranker | 重排序 | 知识服务提供 |
