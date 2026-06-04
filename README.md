# Agent App Factory

> 企业内网 Agent 应用工厂：声明式 `agent.yaml` + Skill → RunSpec → Runner / Tool Gateway

## 项目概述

Agent App Factory 是一个面向企业内网的轻量级 Agent 应用工厂，用于快速生产和管理业务 Agent（合同审查、制度问答、会议纪要、材料起草、舆情简报、合规检查等）。

**核心设计原则**：每个 Agent = 一份配置文件（`agent.yaml`）+ 一个 Skill Package。Skill 不在运行时被动态选择，而是写死在 Agent 配置里。这条规则把所有不确定性赶到边界外，让我们能像生产订单一样批量生产 Agent，又能逐个审计、逐个限流、逐个升级。

- [设计索引](docs/README.md) - 完整技术文档
- [协作说明](CLAUDE.md) - 开发指南
- [需求原文](prd.md) - 产品需求文档

---

## 功能特性

### 🤖 Agent 管理

- **声明式配置**：通过 `agent.yaml` 定义 Agent 的所有行为，包括模型选择、工具权限、知识范围、输出格式、运行限制
- **生命周期管理**：支持 active / cold / archived 三种状态，30天MAU体检机制自动归档低活跃Agent
- **版本管理**：支持灰度发布、一键回滚，RunSpec钉死版本确保会话一致性
- **56个预置Agent App**：开箱即用，覆盖合同审查、会议纪要、工作总结、商业演示、短剧编剧、小红书文案、抖音脚本、故事创作、调研报告、项目提案、规划报告、领导讲话稿、官方文件、AI产品设计、知识产权检索与评估等业务场景

### 🧩 Skill Package 系统

- **插件化能力包**：每个Agent绑定一个Skill Package，包含SKILL.md主文档、references/参考文档、schemas/输出结构、scripts/受控脚本、evals/评测用例
- **Progressive Disclosure**：按需加载，always级别的引用编译时注入，on_demand级别运行时按需读取
- **企业治理层**：enterprise.yaml提供工具依赖、知识范围建议、脚本策略、风险等级等企业级配置
- **Skill评估门禁**：CI集成的Skill评测流水线，支持JSONL评测格式、RPM隔离，确保Skill质量

### 🔧 Tool Gateway

- **权限硬校验**：每次工具调用都校验身份、Agent ID、RunSpec ID、工具权限、输入合法性、数据域权限
- **工具注册表**：平台级工具注册，仅管理员可新增（双签审批），防止攻击面扩大
- **熔断限流**：支持超时控制、频率限制、熔断降级

#### 内置工具列表（约54个工具）

**一、企业知识工具（Enterprise）**

| 工具 ID | 名称 | 描述 | 只读 |
|---------|------|------|-----|
| `kb.search` | 知识库检索 | 内部知识库检索 | ✅ |
| `doc.extract` | 文档解析 | 解析用户上传附件 | ✅ |
| `read_reference` | Skill 引用 | 读取 Skill 包 reference | ✅ |
| `risk.rule_check` | 规则扫描 | 条款风险规则扫描 | ✅ |

**二、文件系统工具（Filesystem）**

| 工具 ID | 名称 | 描述 |
|---------|------|------|
| `fs.read` | 读取文件 | 读取工作区文本文件 |
| `fs.write` | 写入文件 | 创建或覆盖文件 |
| `fs.edit` | 编辑文件 | 定点替换编辑 |
| `fs.apply_patch` | 应用补丁 | 应用 unified diff 补丁 |
| `fs.glob` | Glob | 按模式列出文件 |
| `fs.grep` | Grep | 内容搜索 |

**三、运行时工具（Runtime）**

| 工具 ID | 名称 | 描述 |
|---------|------|------|
| `shell.exec` | Shell | 执行 shell 命令 |
| `shell.process` | 进程管理 | 查看/管理后台进程 |
| `runtime.code_execution` | 代码沙箱 | 隔离环境代码执行 |

**四、Web 工具（Web）**

| 工具 ID | 名称 | 描述 | 只读 |
|---------|------|------|-----|
| `web.search` | 网页搜索 | 百度千帆全网搜索 | ✅ |
| `web.fetch` | 网页抓取 | HTTP GET 获取页面 | ✅ |
| `web.x_search` | X 搜索 | 搜索 X/Twitter 帖子 | ✅ |

**五、飞书工具（Feishu/Lark）**

| 工具 ID | 名称 | 描述 |
|---------|------|------|
| `feishu.doc` | 飞书云文档 | 飞书云文档读写（read/write/append/create/list_blocks） |

**六、MCP · Context7 文档工具**

| 工具 ID | 名称 | 描述 | 只读 |
|---------|------|------|-----|
| `mcp.context7.resolve_library_id` | Context7 库 ID | 解析库名到 Context7 library ID | ✅ |
| `mcp.context7.query_docs` | Context7 文档 | 查询库文档与示例 | ✅ |

**七、MCP · Playwright 浏览器工具**

| 工具 ID | 名称 | 描述 |
|---------|------|------|
| `mcp.playwright.navigate` | 浏览器导航 | 打开 URL |
| `mcp.playwright.snapshot` | 页面快照 | 获取可访问性树/页面结构 | ✅ |
| `mcp.playwright.click` | 点击元素 | 点击页面元素 |
| `mcp.playwright.fill` | 填写表单 | 向输入框填写文本 |

**八、Agent / 子代理工具（Agents）**

| 工具 ID | 名称 | 描述 |
|---------|------|------|
| `agent.spawn` | 子 Agent | 派生子 Agent 执行独立任务并返回结果 |
| `agent.list` | Agent 列表 | 列出可用 Agent App | ✅ |
| `agents.update_plan` | 更新计划 | 更新 Agent 任务计划步骤 |

**九、记忆工具（Memory）**

| 工具 ID | 名称 | 描述 | 只读 |
|---------|------|------|------|
| `memory.search` | 记忆搜索 | 语义/FTS 搜索 MEMORY.md 与会话记忆 | ✅ |
| `memory.get` | 读取记忆 | 读取记忆 markdown 片段 | ✅ |

**十、会话工具（Session）**

| 工具 ID | 名称 | 描述 | 只读 |
|---------|------|------|------|
| `sessions.list` | 会话列表 | 列出用户会话 | ✅ |
| `sessions.history` | 会话历史 | 读取会话 transcript | ✅ |
| `sessions.send` | 发送消息 | 向另一会话发消息并可选等待回复 |
| `sessions.spawn` | 创建子会话 | 创建子 Agent 会话执行任务 |
| `sessions.yield` | Yield | 结束 turn 并传递 yield 消息 |
| `sessions.subagents` | 子代理列表 | 列出当前会话下的 subagent runs | ✅ |
| `sessions.status` | 会话状态 | 查询会话元数据与运行状态 | ✅ |

**十一、UI 工具**

| 工具 ID | 名称 | 描述 |
|---------|------|------|
| `ui.browser` | 浏览器 | 统一 browser 工具（Playwright MCP） |
| `ui.canvas` | Canvas | Canvas/A2UI 控制 |

**十二、自动化工具（Automation）**

| 工具 ID | 名称 | 描述 |
|---------|------|------|
| `automation.cron` | 定时任务 | Cron 调度 CRUD |
| `automation.gateway` | Gateway | Gateway 状态与配置查询 | ✅ |
| `automation.heartbeat_respond` | 心跳响应 | 记录 heartbeat 结果 |

**十三、消息工具（Messaging）**

| 工具 ID | 名称 | 描述 |
|---------|------|------|
| `messaging.message` | 发送消息 | 向会话/渠道发送消息（send/read/broadcast） |

**十四、Nodes 工具**

| 工具 ID | 名称 | 描述 |
|---------|------|------|
| `nodes.manage` | Nodes | Nodes + 设备管理 |

**十五、媒体工具（Media）**

| 工具 ID | 名称 | 描述 |
|---------|------|------|
| `media.image` | 图像理解 | VLM 图像描述 | ✅ |
| `media.image_generate` | 图像生成 | 图像生成 |
| `media.music_generate` | 音乐生成 | 音乐生成 |
| `media.video_generate` | 视频生成 | 视频生成 |
| `media.pdf` | PDF 分析 | 提取并分析 PDF | ✅ |
| `media.tts` | 文字转语音 | TTS 语音合成 |

#### 工具预设（Tool Presets）

| Preset | 说明 | 包含工具 |
|--------|------|---------|
| `minimal` | 精简 | kb.search, doc.extract, read_reference |
| `coding` | 代码开发 | 文件系统 + Shell + Web + Memory + Sessions + Context7 |
| `messaging` | 企业知识 | 企业知识 + 搜索 + 子 Agent |
| `enterprise` | 企业知识+ | 企业知识（全部4个） |
| `web` | 网页检索 | 搜索 + 抓取 + Context7 |
| `browser` | 浏览器自动化 | Web + Playwright MCP |
| `agents` | 多 Agent | 子 Agent 编排 + 企业知识 |
| `full` | 全量（已实现） | 所有已实现的内置工具 |
| `openclaw` | OpenClaw 完整 | Memory + Sessions + UI + Automation + Media + Coding 等 |

#### 工具组（Tool Groups）

工具可以通过组名批量引用：

- `group:openclaw` - OpenClaw 所有已实现工具
- `group:filesystem` - 文件系统工具（6个）
- `group:runtime` - 运行时工具（3个）
- `group:web` - Web工具（3个）
- `group:enterprise` - 企业知识工具（4个）
- `group:feishu` - 飞书工具（1个）
- `group:mcp_context7` - Context7 MCP（2个）
- `group:mcp_playwright` - Playwright MCP（4个）
- `group:agents` - Agent工具（3个）
- `group:memory` - 记忆工具（2个）
- `group:sessions` - 会话工具（7个）
- `group:ui` - UI工具（2个）
- `group:automation` - 自动化工具（3个）
- `group:messaging` - 消息工具（1个）
- `group:nodes` - Nodes工具（1个）
- `group:media` - 媒体工具（6个）

#### OpenClaw 统一工具调度

OpenClaw 是整合了30+工具的统一调度层，提供以下工具集合：

- **记忆工具（Memory）**：语义搜索、记忆片段读取
- **会话工具（Session）**：列表、历史、发送、创建子会话、yield、状态查询
- **UI工具**：浏览器自动化、Canvas控制
- **自动化工具**：定时任务、Gateway、心跳响应
- **媒体工具**：图像理解/生成、音乐生成、视频生成、PDF分析、TTS
- **运行时工具**：代码沙箱执行

### 📊 模型网关与队列

- **多模型路由**：支持默认模型+fallback模型+低コスト模型三级切换
- **Token预算控制**：按部门、用户、Agent多维度控制
- **高峰期降级**：LLM队列延迟超阈值时自动降级（跳过rerank→降低检索top_k→切换小模型→限制max_turns）
- **优先级队列**：interactive（交互式）/ document（文档）/ batch（批处理）/ privileged（特权）

### 🛡️ 安全与审计

- **三档审计**：minimal（默认）/ standard / full，支持工具轨迹、检索ID、成本等最小留痕
- **RBAC权限模型**：基于角色和数据域的访问控制
- **JWT短令牌认证**：5分钟有效期，一次性使用，portal单点登录集成
- **工具双签审批**：新工具注册需要双重审批，防止攻击面扩大

### 💬 Chat Widget 前端

- **独立子站部署**：部署在 agent.company.com，通过新tab打开
- **SSE流式输出**：实时流式对话体验
- **分层存储**：
  - localStorage：轻偏好（最近Agent、UI设置、收藏）
  - IndexedDB（dexie.js）：对话历史，30天TTL，可选加密
  - 敏感文件：仅会话内存，关tab即清
- **HTML演示文稿实时预览**：内置HtmlDeckPreview组件，支持在生成过程中实时预览HTML幻灯片

### 📑 飞书（Feishu/Lark）集成

完整的飞书渠道集成，支持在飞书群聊中直接使用Agent：

**核心功能**：
- **命令交互**：支持 `/agent`、`/agents list`、`/help` 等命令
- **会话绑定**：自动绑定Agent与飞书会话
- **长任务续继**：支持"继续"命令，在同一会话中继续执行长任务
- **最大轮次限制**：FEISHU_MAX_TURNS 配置，防止无限循环

**技术实现**：
- `feishu_client.py` - 飞书API客户端（lark-oapi）
- `feishu_doc_tools.py` - 飞书云文档读写
- `feishu_service.py` - 会话绑定、Agent路由、聊天执行
- `feishu_transport.py` - 传输层
- `feishu_events.py` - 飞书事件处理

### 📊 商业演示文稿生成器（HTML幻灯片）

`business-presentation-generator-agent` 是专业的HTML演示文稿生成Agent，生成自包含的单文件HTML幻灯片：

**特点**：
- 自包含（无CDN依赖，本地字体打包）
- 投影仪友好（3米外可读）
- 打印为PDF兼容（@media print）
- 实时预览（在Widget中生成过程中即可预览）

**5步交互流程**：
1. 收集需求（collect requirements）
2. 视觉设计（visual design）
3. 大纲生成（outline）
4. 分段生成（segment-generate）
5. 调整优化（adjust）

**视觉风格**：
- 12种预设风格（Bold Signal / Swiss Modern / Neon Cyber / Paper & Ink 等）
- 14种高级CSS效果（极光 / 玻璃拟态 / 光球 等）
- HSL品牌色彩微调
- 深色/浅色主题

**输出规范**：
- 严格内容密度控制
- 55项输出检查清单

### 🎬 内容创作Agent套件

**短视频/短剧**：
| Agent | 功能 |
|-------|------|
| `short-drama-scriptwriter-agent` | 情感驱动的短剧脚本 |
| `short-drama-planner-agent` | 短剧规划 |
| `short-drama-evaluator-agent` | 脚本评估 |
| `tiktok-script-agent` | 抖音脚本撰写 |
| `script-evaluation-agent` | 脚本评估 |

**社交媒体**：
| Agent | 功能 |
|-------|------|
| `xhs-writing-agent` | 小红书文案生成 |
| `xhs-search-agent` | 小红书内容检索 |
| `wechat-article-agent` | 微信公众号文章 |

**故事创作**：
- `story-synopsis-agent` - 故事梗概
- `story-character-profile-agent` - 角色设定
- `story-plot-points-agent` - 情节要点
- `story-genre-extraction-agent` - 类型提取
- `story-evaluation-agent` - 故事评估
- 故事关系、背景等Agent

**商业文档**：
| Agent | 功能 |
|-------|------|
| `work-summary-agent` | 周报/月报/年报 |
| `leadership-speech-agent` | 领导讲话稿 |
| `official-document-agent` | 官方文件润色 |
| `research-report-agent` | 调研报告 |
| `project-proposal-agent` | 项目提案 |
| `planning-report-agent` | 规划报告 |

### 🔍 业务Agent（56个）

开箱即用的业务Agent：

| Agent | 功能 |
|-------|------|
| `contract-review-agent` | 合同审查 |
| `meeting-minutes-agent` | 会议纪要 |
| `work-summary-agent` | 工作总结 |
| `business-presentation-generator-agent` | HTML演示文稿 |
| `code-assistant-agent` | 代码助手 |
| `facts-agent` | 事实核查 |
| `ai-product-design-agent` | AI产品设计 |
| `ip-search-agent` | 知识产权检索 |
| `ip-evaluation-agent` | 知识产权评估 |

### ⏰ 定时任务与自动化

- **Cron调度**：通过 `automation.cron` 工具在聊天中管理定时任务
- **心跳响应**：`automation.heartbeat_respond` 记录心跳结果
- **Gateway查询**：`automation.gateway` 查询网关状态
- **Agent级Cron**：支持为单个Agent设置定时任务
- **后台调度器**：`cron_scheduler.py` 后台Worker

### 🗄️ 文档处理Worker

- **异步文档解析**：Redis队列 + Worker模式
- **支持格式**：PDF（通过pypdf）
- **文件大小阈值**：`DOC_PARSE_ASYNC_MIN_BYTES` 配置
- `document_parser_worker.py` - 异步文档解析Worker
- `doc_queue.py` - Redis文档任务队列

### 📈 管理后台

完整的React管理后台，包含10+管理页面：

- **Agent管理**：启停、配置、版本
- **Skill管理**：CRUD、tar.gz包上传解析
- **工具注册**：审批工作流
- **策略管理**：平台级/组织级
- **配额管理**：Token配额、作用域控制
- **用户管理**：角色编辑、部门管理
- **审计日志**：查看、CSV导出
- **会话追踪**：完整会话检查
- **降级控制**：高峰期降级配置
- **指标面板**：系统/业务指标

### 💾 存储架构

- **PostgreSQL**：主数据库（SQLAlchemy + Alembic迁移）
  - 表：agent_apps, chat_session, run_spec, checkpoint, transcript, audit, tool_approval_log, synced_user, synced_department, quota, agent_cron_job, agent_version, system
- **Redis**：队列、限流、会话锁、缓存（Streams模式）
- **本地/对象存储**：文件存储（MinIO配置）

---

## 技术架构

### 系统架构图

```
┌──────────────────────────────────────────────────────────────┐
│                     用户 / 业务系统 / 飞书                      │
└─────────────────────────┬────────────────────────────────────┘
                          ↓
┌─────────────────────────┴────────────────────────────────────┐
│              API 网关 / SSO / RBAC                           │
│              (认证、入口限流、部门识别)                        │
└─────────────────────────┬────────────────────────────────────┘
                          ↓
┌─────────────────────────┴────────────────────────────────────┐
│              Agent App 注册中心                              │
│              (Agent配置、版本、启停、权限)                     │
└─────────────────────────┬────────────────────────────────────┘
                          ↓
┌─────────────────────────┴────────────────────────────────────┐
│              Skill Compiler（装配车间）                       │
│              (Agent + Skill + 权限 + 工具策略 → RunSpec)     │
└─────────────────────────┬────────────────────────────────────┘
                          ↓
┌─────────────────────────┴────────────────────────────────────┐
│              RunSpec 出厂订单                                │
│              (prompt_parts、allowed_tools、retrieval_scopes) │
└─────────────────────────┬────────────────────────────────────┘
                          ↓
┌─────────────────────────┴────────────────────────────────────┐
│              共享 Agent Runner                               │
│              (工具调用循环、多轮对话、上下文治理)              │
└─────────────┬───────────────────────────┬───────────────────┘
              ↓                           ↓
┌─────────────────────────┐   ┌──────────────────────────────┐
│      模型网关 / 队列      │   │        Tool Gateway         │
│  (模型路由、fallback、    │   │   (工具注册、权限校验、       │
│   token预算、限流)        │   │    审计、超时、熔断)         │
└─────────────────────────┘   └──────────┬───────────────────┘
                                          ↓
                         ┌──────────────────────────────┐
                         │        知识服务（外部）        │
                         │   (向量检索、文档解析、OCR)    │
                         │        内部API               │
                         │        受控脚本Worker        │
                         └──────────────────────────────┘
```

### 核心模块

| 模块 | 职责 | 类比 |
|------|------|------|
| API 网关 | 认证、识别部门、入口限流 | 公司大门保安 |
| Agent App 注册中心 | 管 Agent 配置、版本、启停、权限 | 岗位说明书档案室 |
| Skill Compiler | 把 Agent + Skill + 权限 + 工具策略编译成 RunSpec | 装配车间 |
| Agent Runner | 执行工具调用循环和轻量编排 | 流水线工人 |
| Tool Gateway | 工具注册、权限校验、审计、超时、熔断 | 楼里每个工具室门口的安检门 |
| 模型网关 / 队列 | 模型路由、限流、fallback、token 预算 | 调度中心 |
| 知识服务（外部） | 向量检索、关键词检索、rerank、数据域过滤 | 外协的资料室 |
| 受控脚本 Worker 池 | 跑受控脚本，不按用户起容器 | 共享的临时实验室 |
| 审计 / 日志 | 工具轨迹、输入输出、成本、错误、复现信息 | 监控录像 |
| 飞书集成层 | 飞书消息接收、命令处理、会话绑定 | 飞书渠道入口 |
| 文档解析Worker | 异步文档解析任务处理 | 文档加工车间 |

### 技术栈

#### 后端（Python）

- **框架**：FastAPI + uvicorn
- **数据库**：PostgreSQL + SQLAlchemy + alembic
- **缓存/队列**：Redis（ Streams 模式）
- **认证**：PyJWT（短令牌交换）
- **飞书SDK**：lark-oapi
- **文档解析**：pypdf
- **可观测性**：Prometheus FastAPI Instrumentator
- **可选**：OpenTelemetry

主要依赖：
```
fastapi>=0.115, uvicorn>=0.32, sqlalchemy>=2.0, alembic>=1.13,
asyncpg>=0.29, psycopg>=3.1, redis>=5.0, pydantic-settings>=2.5,
PyJWT>=2.9, httpx>=0.27, python-multipart>=0.0.9, lark-oapi>=1.0,
pypdf>=4.0
```

#### 前端（TypeScript/React）

- **框架**：React 18 + TypeScript
- **路由**：React Router DOM 6
- **状态管理**：Zustand 5
- **样式**：TailwindCSS + shadcn/ui
- **存储**：dexie.js（IndexedDB封装）
- **构建**：Vite 6

主要依赖：
```
react>=18.3, react-dom>=18.3, react-router-dom>=6.27,
zustand>=5.0, dexie>=4.0, react-markdown>=10.1,
tailwindcss>=3.4, vite>=6.0, typescript>=5.6
```

---

## 项目结构

```
agent-factory/
├── agents/                    # Agent App 集合（每个Agent一个目录）
│   ├── contract-review-agent/         # 合同审查Agent
│   │   ├── agent.yaml                 # Agent配置（岗位说明书）
│   │   └── skill/                      # Skill Package（操作手册）
│   │       ├── SKILL.md                # 唯一强制入口
│   │       ├── references/             # 参考文档（按需加载）
│   │       ├── schemas/               # 输出格式定义
│   │       ├── scripts/                # 受控脚本
│   │       └── evals/                  # 评测用例
│   ├── meeting-minutes-agent/         # 会议纪要Agent
│   ├── facts-agent/                    # 事实核查Agent
│   └── ...（共56个Agent）
│
├── backend/                   # 后端服务
│   ├── src/agent_factory/
│   │   ├── api/               # API路由
│   │   │   ├── v1/            # v1版本API
│   │   │   │   ├── agents.py
│   │   │   │   ├── skills.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── admin.py
│   │   │   │   └── ...
│   │   │   └── health.py
│   │   ├── core/              # 核心逻辑
│   │   │   ├── compiler.py    # Skill Compiler
│   │   │   ├── runspec_v2.py  # RunSpec定义
│   │   │   ├── agent_runner.py
│   │   │   └── ...
│   │   ├── services/          # 业务服务
│   │   │   ├── model_gateway.py
│   │   │   ├── tool_gateway.py
│   │   │   ├── skill_bundle_storage.py
│   │   │   ├── feishu_client.py       # 飞书API客户端
│   │   │   ├── feishu_doc_tools.py   # 飞书云文档
│   │   │   ├── feishu_service.py     # 飞书服务
│   │   │   ├── feishu_transport.py   # 飞书传输层
│   │   │   ├── feishu_events.py      # 飞书事件处理
│   │   │   └── ...
│   │   ├── infra/             # 基础设施
│   │   │   ├── redis.py
│   │   │   ├── db.py
│   │   │   ├── jwt_tokens.py
│   │   │   └── ...
│   │   ├── db/                # 数据模型
│   │   │   ├── models/        # SQLAlchemy模型
│   │   │   └── base.py
│   │   ├── workers/           # 后台Worker
│   │   │   ├── model_worker.py
│   │   │   ├── audit_worker.py
│   │   │   ├── document_parser_worker.py  # 文档解析Worker
│   │   │   ├── cron_scheduler.py            # Cron调度器
│   │   │   └── ...
│   │   └── config/            # 配置
│   │       └── settings.py
│   ├── tests/                 # 测试
│   │   ├── unit/
│   │   └── integration/
│   ├── scripts/               # 工具脚本
│   │   ├── sync_agents_from_repo.py    # 同步Agent
│   │   ├── sync_skills_from_repo.py    # 同步Skill
│   │   ├── run_skill_eval.py           # Skill评测
│   │   ├── validate_skill_md_files.py  # Skill验证
│   │   └── init_db.py                  # 数据库初始化
│   ├── alembic/               # 数据库迁移
│   └── pyproject.toml
│
├── frontend/                  # 前端（Chat Widget）
│   ├── src/
│   │   ├── api/               # API客户端
│   │   │   ├── agents.ts
│   │   │   ├── auth.ts
│   │   │   ├── client.ts
│   │   │   └── sse.ts
│   │   ├── components/        # React组件
│   │   │   ├── chat/         # 聊天相关组件
│   │   │   │   ├── HtmlDeckPreview.tsx   # HTML幻灯片预览
│   │   │   │   ├── HtmlPreviewFrame.tsx # HTML预览框架
│   │   │   │   └── MessageBubble.tsx     # 消息气泡
│   │   │   ├── layout/        # 布局组件
│   │   │   ├── pages/         # 页面组件
│   │   │   └── apps/          # 应用管理组件
│   │   ├── hooks/             # 自定义Hooks
│   │   ├── stores/            # Zustand状态
│   │   ├── lib/               # 工具函数
│   │   │   └── htmlPreview.ts  # HTML检测与合并
│   │   ├── types/             # TypeScript类型
│   │   └── db/                # IndexedDB封装
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
│
├── docs/                      # 技术文档（49个文档）
│   ├── 01-overview.md         # 项目概述
│   ├── 02-architecture.md     # 架构设计
│   ├── 03-agent-app-spec.md   # Agent规范
│   ├── 04-skill-package-spec.md
│   ├── 05-runspec.md
│   ├── 06-api-gateway.md
│   ├── ...（共49个文档）
│   └── README.md               # 文档索引
│
├── prd.md                     # 产品需求文档
├── CLAUDE.md                  # 协作说明
└── README.md                  # 本文件
```

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Redis 6+

### 后端设置

```bash
cd backend

# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 配置数据库和Redis连接

# 数据库迁移
uv run alembic upgrade head

# 启动服务
uv run uvicorn agent_factory.main:app --reload --port 8000
```

### 前端设置

```bash
cd frontend

# 安装依赖
npm install

# 配置环境变量
cp .env.example .env
# 编辑 .env 配置API地址

# 启动开发服务器
npm run dev
```

### 启动完整开发环境

```bash
# 根目录下执行
./scripts/bootstrap-dev.sh
```

---

## 使用流程

### 1. 用户访问Agent

```
用户在 portal 点击"合同审查助手"
       ↓
portal 后端用现有 portal-JWT 调 /auth/exchange 接口
       ↓
换取 5 分钟有效的 short-lived JWT（绑定 agent_id + user_id + 部门 + 权限）
       ↓
portal 前端 window.open(URL, '_blank') 开新tab
       ↓
widget 加载 → 从 URL 取 token → 验签 → 建立 session
       ↓
立刻从 URL 删除 token（防历史记录泄露）
       ↓
用 session cookie 调 API
```

### 2. 请求执行流程

```
1. 用户选 Agent App
2. API 网关认证 + 识别部门 + 基础限流
3. Agent 注册中心加载 agent.yaml
4. Skill Compiler 加载 Skill，生成 RunSpec
5. Agent Runner 跑工具调用循环
6. Tool Gateway 执行检索 / 文档解析 / 规则检查 / 内部 API / 受控脚本
7. 模型网关调模型并 fallback
8. 输出按 schema 校验
9. 审计记录
```

### 3. RunSpec（出厂订单）

RunSpec 是每次请求的"出厂订单"，包含：

```yaml
run_id: run_20260506_001
agent_id: contract-review-agent
agent_version: 0.1.0
user_id: u123
department: legal

prompt_parts:
  - platform_policy
  - org_policy
  - agent_instruction
  - skill_clause_review

allowed_tools:
  - kb.search
  - doc.extract
  - risk.rule_check

retrieval_scopes:
  - group_legal_policy
  - contract_templates

runtime:
  model: qwen3-32b
  fallback_model: qwen3-14b
  max_turns: 6
  timeout_seconds: 90
  max_tokens: 8000
```

**核心特性**：RunSpec一旦生成就不能修改，保证审计可复现、权限收敛、升级安全。

---

## Agent 开发

### 创建新Agent

1. 在 `agents/` 目录下创建Agent目录
2. 编写 `agent.yaml` 配置文件
3. 创建 `skill/` 目录并编写 SKILL.md
4.（如需要）添加 references/、schemas/、scripts/、evals/
5. 提交到仓库，部署时自动注册

### agent.yaml 示例

```yaml
id: contract-review-agent
name: 合同审查助手
description: 审查集团内部合同文本的风险，给修改建议
owner: legal-department
version: "0.1.0"
runspec_schema_version: 1

model_policy:
  default: qwen3-32b
  fallback: qwen3-14b
  low_cost: qwen3-8b

skill:
  id: clause-review
  version_pin: "0.1.0"

tools:
  allow:
    - kb.search
    - doc.extract
    - risk.rule_check

knowledge_scopes:
  - group_legal_policy
  - contract_templates
  - historical_contract_cases

output_schema: contract-review-report

limits:
  max_turns: 6
  max_tokens: 8000
  timeout_seconds: 90

audit:
  level: minimal
  trace_prompt: false
  trace_tool_calls: true
  trace_retrieval_ids: true
  retain_days: 90

ui_config:
  title: 合同审查助手
  avatar: /static/agents/contract.png
  welcome_message: |
    我可以帮你审查合同关键条款，识别风险并给出修改建议。
  input_placeholder: 上传合同或粘贴条款...
  quick_actions:
    - label: 审查全文
      prompt: "请审查整份合同的所有关键条款"
  attachments:
    enabled: true
    accept: [.docx, .pdf, .txt]
    max_size_mb: 10
```

### SKILL.md 示例

```yaml
---
name: clause-review
description: 审查合同关键条款，给风险等级、依据和修改建议。用于合同审查、条款风险识别、法务修改建议、合同模板比对。
when_to_use: 用户上传合同、问条款风险、要法务审查意见、要对照公司模板时使用。
---

# 合同条款审查

你负责审查合同关键条款，包括付款、违约、保密、知识产权、争议解决、不可抗力、终止。

执行要求：

1. 先识别合同类型、主体、金额、期限、关键义务
2. 对关键条款逐项判断风险等级
3. 必须引用公司制度、模板条款或历史案例作为依据
4. 每个风险点必须给出可落地的修改建议
5. 不确定时明确标记"需人工复核"，不要编造依据

## 配套文件

- `reference.md`：审查方法和风险等级说明
- `examples.md`：报告示例和条款修改示例
- `references/checklist.md`：分类型审查清单
```

---

## 配置与维护

### 环境变量

#### 后端（backend/.env）

```bash
# 数据库
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/agent_factory

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256

# 模型配置
MODEL_GATEWAY_URL=https://your-model-gateway.com
DEFAULT_MODEL=qwen3-32b

# 文件存储（MinIO）
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=your-access-key
MINIO_SECRET_KEY=your-secret-key

# 飞书配置
FEISHU_APP_ID=your-feishu-app-id
FEISHU_APP_SECRET=your-feishu-app-secret
FEISHU_MAX_TURNS=64

# 文档解析
DOC_PARSE_ASYNC_MIN_BYTES=1048576

# 功能开关
MEDIA_TOOLS_ENABLED=true
AUTOMATION_TOOLS_ENABLED=true
MESSAGING_TOOLS_ENABLED=true
```

#### 前端（frontend/.env）

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_WS_URL=ws://localhost:8000
```

### 数据库迁移

```bash
# 创建新迁移
uv run alembic revision --autogenerate -m "add user preferences table"

# 应用迁移
uv run alembic upgrade head

# 回滚
uv run alembic downgrade -1
```

---

## API 接口

### 核心接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /auth/exchange | JWT短令牌交换 |
| GET | /api/v1/agents | 列出有权限的Agent |
| POST | /api/v1/agents/{agent_id}/init | 初始化Agent会话 |
| POST | /api/v1/chat/stream | SSE流式对话 |
| GET | /api/v1/agents/{agent_id}/ui_config | 获取UI配置 |

### 管理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/admin/agents | 管理后台-Agent列表 |
| PUT | /api/v1/admin/agents/{agent_id} | 更新Agent配置 |
| GET | /api/v1/admin/skills | Skill列表 |
| POST | /api/v1/admin/tools | 注册新Tool（需管理员） |
| GET | /api/v1/admin/audit | 审计日志 |

详见 [API接口参考](docs/19-api-reference.md)

---

## 开发指南

### 代码规范

- Python：遵循 PEP 8，使用 ruff 检查，mypy 严格模式
- TypeScript：遵循 ESLint 规则，React Hooks 规范
- Git：conventional commits，PR 必须有 review

详见 [代码规范](docs/43-code-guidelines.md)

### 测试

```bash
# 后端单元测试
cd backend
uv run pytest tests/unit/

# 后端集成测试
uv run pytest tests/integration/

# 前端单元测试
cd frontend
npm run test

# E2E测试
npm run test:e2e
```

### 调试

```bash
# 后端热重载
uv run uvicorn agent_factory.main:app --reload

# 前端热重载
npm run dev

# 查看日志
tail -f backend.log
```

详见 [开发快速启动指南](docs/35-quickstart.md)

---

## 部署

### Docker 部署

```bash
# 构建镜像
docker build -t agent-factory:latest .

# 运行容器
docker run -d -p 8000:8000 \
  --env-file backend/.env \
  agent-factory:latest
```

### Kubernetes 部署

```bash
# 应用manifest
kubectl apply -f k8s/

# 查看状态
kubectl get pods -n agent-factory
```

详见 [K8s部署清单](docs/40-k8s-manifests.md)

### 生产环境检查清单

详见 [生产环境部署 Checklist](docs/37-production-checklist.md)

---

## 监控与运维

### 指标

- 系统层：QPS、P50/P95/P99延迟、错误率、队列长度、资源池利用率
- Agent层：每个Agent的请求量/错误率/P99、token消耗trend
- 业务层：DAU/MAU、每日新增Agent数、每日新增对话数、用户反馈率

### 告警

- LLM队列P99延迟>30s：跳过rerank
- LLM队列P99延迟>60s：检索top_k从20降到5
- LLM队列P99延迟>120s：切换小模型
- 错误率>5%：限制max_turns到3

详见 [可观测性设计](docs/32-observability-design.md)

### 故障排查

详见 [故障排查手册](docs/36-troubleshooting.md)

---

## 路线图

### P0（当前）：声明式Agent App + 用户入口

- Agent App Manifest
- 静态 Skill Package 绑定
- 简单工具调用循环
- 基础知识检索工具
- 最小审计（minimal级）
- `/auth/exchange` JWT短令牌交换接口
- Embeddable Chat Widget MVP

### P1：工具绑定的Skill

- SKILL.md frontmatter完整化
- enterprise.yaml
- Tool Gateway权限交集
- schema校验
- 评测用例

### P2：受控脚本

- 受控的预处理/后处理脚本
- 脚本Worker池
- 脚本manifest
- 超时、无网络、临时文件系统

### P3：工作流Skill和Router Agent

- Skill声明小型DAG
- Agent内部轻量步骤编排
- 可选Router Agent选具体Agent App

详见 [P0-P3路线图](docs/14-roadmap.md)

---

## 许可证

本项目仅供内部使用。