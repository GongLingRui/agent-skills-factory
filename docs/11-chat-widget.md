# 11. Chat Widget 前端设计

> 版本：v0.6 · 2026-05-06

---

## 入口模式：独立子站 + 新 tab

现有 portal 已经做好 SSO（JWT）+ RBAC + 应用启动器，原来是点击应用跳 dify URL 进 dify 自带的聊天 UI。**替换 dify 之后，chat UI 这一块必须自建，不然 portal 在用户视角下就是个空壳子**。

### 设计

- **widget 是独立子站**，部署在 agent.company.com（与 portal 不同 origin，localStorage 自然隔离）
- portal 点击应用 → window.open(URL, '_blank') 开**新 tab**
- widget 通过 JWT 短令牌从 portal 安全继承用户身份和权限

**类比**：像央企 OA 里点"差旅报销" → 新 tab 跳到差旅系统，差旅系统继承 OA 的登录态。用户感知跟之前点 dify 链接一样。

### 标准 URL 模式

```
https://agent.company.com/apps/<agent_id>?token=<short-lived-JWT>
```

token 是 **5 分钟有效**的一次性令牌，widget 加载后立即从 URL 移除（防历史记录泄露）。

---

## 用户完整路径

1. 用户在 portal 点击"合同审查助手"
2. portal 后端：用现有 portal-JWT 调 /auth/exchange 接口
   → 换一个 **5 分钟有效**的 short-lived JWT
   → JWT 绑定 agent_id + user_id + 部门 + 权限
3. portal 前端：window.open(URL, '_blank')
4. widget 加载 → 从 URL 取 token → 验签 → 建立 session
   → **立刻从 URL 删除 token**（防历史记录泄露）
   → 用 session cookie 调 API
5. 用户对话，widget 把历史存 IndexedDB（轻偏好如收藏、主题存 localStorage，见 §10.3 分层存储）
6. 用户关 tab，session 失效，下次重新换新 token

详细 SSO / JWT 流程见 [06-api-gateway.md](06-api-gateway.md)。

---

## Widget 内部布局

最小可用版本：

> **顶栏**：Agent 名称 + 头像 + 当前用户 + 关闭按钮
> **中区**：消息流（流式 SSE 渲染）
> **底栏**：输入框 + 发送 + 上传文件 + 快捷指令按钮（可选）
> **侧栏（可折叠）**：本地历史对话列表 + 导出 / 导入按钮

历史数据按 [12-security-audit.md](12-security-audit.md) 分层存储策略管理：轻偏好存 localStorage，对话历史存 IndexedDB，敏感文件不落盘。运维 debug 时让用户点"导出"上传 JSON。

---

## Widget 顶栏 Agent 切换（不重开 tab）

类比：**像桌面浏览器的标签页**——一个 widget 实例可以承载多个 Agent，顶栏给一个下拉菜单切换，不用退回 portal 重新打开。

### 切换流程

1. 用户在合同审查中，点顶栏的 Agent 下拉
2. widget 调 GET /api/v1/agents（带 session cookie，按 portal RBAC 过滤）
   → 返回当前用户有权限的所有 Agent 列表（id / name / avatar）
3. 用户选"会议纪要 Agent"
4. widget 调 POST /api/v1/agents/<new_agent_id>/init（session cookie 验权）
   → 后端验权 + 编译新 RunSpec + 返回新 agent 的 ui_config
5. widget 切换上下文：
   - 清空当前消息流
   - 从 localStorage 加载该 agent 的历史（按 §10.3）
   - 按新 ui_config 重新渲染顶栏 / 欢迎语 / 输入框 / 快捷指令

### 关键设计

- **不需要重新换 token**——session cookie 有效期内可以自由切换 Agent
- **每个 agent 历史独立**——切回去能看到之前的对话
- **ui_config 动态渲染**——切换后界面立刻刷新

---

## 最近用过的 Agent 列表

呈现位置：widget 顶栏下拉菜单分两块——**"收藏"** 和 **"最近"**。

```
┌─ Agent 选择 ────────────────────┐
│ ⭐ 收藏                          │
│ • 合同审查助手                   │
│ • 制度问答助手                   │
│ 🕐 最近                          │
│ • 会议纪要（5 分钟前）           │
│ • 材料起草（昨天）               │
│ • 舆情简报（3 天前）             │
│ ───                              │
│ 浏览全部 Agent →                 │
└──────────────────────────────────┘
```

### 设计点

- **数据源 = localStorage**（与对话历史同源，**零服务器查询**）
- **排序**：收藏区按用户拖拽顺序；最近区按最后使用时间倒序
- **上限**：最近保留 10 个，超过 LRU 淘汰
- **收藏**：用户在某 Agent 下点"⭐ 钉到收藏"——这条数据也存 localStorage
- **"浏览全部"**：跳出全 Agent 列表（按 §4.5.5 流程拉服务器列表）

---

## 分层存储设计

> 按数据敏感度分三层：

| 数据类型 | 存哪里 | TTL | 加密 |
|---------|--------|-----|------|
| 轻偏好（最近 Agent / UI 设置 / 收藏 / 主题） | **localStorage** | 永久 | 否 |
| 对话历史（消息文本 / 时间戳） | **IndexedDB**（dexie.js 包装） | 30 天 TTL | 可选 SubtleCrypto |
| 敏感文件内容（合同正文 / 公文附件 / 上传文档） | **不持久化**（仅会话内存） | 关 tab 即清 | N/A |

### 关于 dexie.js / IndexedDB

- **IndexedDB 是浏览器自带的结构化数据库**，跟 localStorage 一样无需安装
- **dexie.js 只是让 IndexedDB 用起来不那么折磨的 JavaScript 库**——作为 widget 前端依赖打包（跟 React、Tailwind 一样），用户访问 widget 时浏览器自动加载，**用户什么都不用装**
- 容量：localStorage 5-10 MB；IndexedDB 几百 MB 到 GB（按浏览器配额）

### 机制

- IndexedDB 用 dexie.js 包装（容量大 / 异步 / 索引查询）
- TTL 由 widget 后台定时任务清理过期记录
- 加密 key 派生自 **用户身份标识**（`user_id_hash = SHA-256(user_id + salt)`），经 PBKDF2（迭代 100000 次）+ 固定平台 salt 派生为 AES-GCM 256 位 key；同一用户的加密数据在所有会话中可解密，换用户或清缓存后不可恢复。用户主动开启加密 = 共享电脑场景下防止其他用户读取本地历史。
- **敏感文件内容不写任何持久化层**——上传后只在会话内存中处理，会话结束 / 关 tab 即释放
- UI 显式提示："本地存储 30 天后自动清理。共享电脑请勾选退出时清除会话。"

### 好处

- 服务器零业务存储成本
- 合规边界干净（轻偏好 + 对话历史在用户终端，敏感文件不落任何盘）
- 央企共享电脑场景下，敏感数据不会被下一个用户翻出来

### 剩余风险与边界

- **跨设备失效**：用户换电脑会丢历史——提供 export/import JSON 手动迁移
- **用户主动清缓存 / 浏览器清理**：UI 显式提示
- **IndexedDB 加密为可选**：用户开了忘了密码 = 数据废掉；不开 = 共享电脑可见

### 与服务器审计的协调

本地存储路线**不与 minimal 审计冲突**。服务器仍记录关键审计事件的最小元数据（工具调用、异常、错误码），但不含 prompt / output 内容。详见 [12-security-audit.md](12-security-audit.md)。

---

## 消息对象 Schema 与 IndexedDB 结构

### 单条消息格式（TypeScript 接口）

```typescript
interface ChatMessage {
  message_id: string;           // 全局唯一，如 msg_007
  role: "user" | "assistant" | "tool" | "system";
  content: string;              // 文本内容（tool 角色时为 tool_result JSON）
  created_at: number;           // 时间戳（ms）

  // assistant 消息特有
  tool_calls?: ToolCall[];      // 模型发起的工具调用
  schema_valid?: boolean | null; // schema 校验结果
  feedback?: "thumbs_up" | "thumbs_down" | null;

  // tool 消息特有
  tool_call_id?: string;
}

interface ToolCall {
  id: string;
  type: "function";
  function: {
    name: string;
    arguments: string; // JSON string
  };
}
```

### IndexedDB 表结构（dexie.js 定义）

```typescript
import Dexie from 'dexie';

class WidgetDB extends Dexie {
  sessions!: Dexie.Table<SessionRecord, string>;
  messages!: Dexie.Table<MessageRecord, string>;

  constructor() {
    super('AgentFactoryWidget');
    this.version(1).stores({
      sessions: 'session_id, agent_id, updated_at',
      messages: 'message_id, session_id, [session_id+created_at]'
    });
  }
}

interface SessionRecord {
  session_id: string;
  agent_id: string;
  run_id: string;
  title: string;           // 首条用户消息前 20 字，用于历史列表展示
  status: 'running' | 'completed' | 'error';
  created_at: number;
  updated_at: number;
}

interface MessageRecord {
  message_id: string;
  session_id: string;
  role: string;
  content: string;
  created_at: number;
  tool_calls?: string;     // JSON 序列化
  schema_valid?: boolean | null;
  feedback?: string | null;
}
```

### Export / Import JSON 格式

**导出文件结构**（`agent-history-YYYYMMDD.json`）：

```json
{
  "version": "1.0",
  "exported_at": "2026-05-07T14:30:00Z",
  "user_id_hash": "a1b2c3...",
  "sessions": [
    {
      "session_id": "sess_abc123",
      "agent_id": "contract-review-agent",
      "title": "审查合同付款条款",
      "messages": [
        {
          "message_id": "msg_001",
          "role": "user",
          "content": "请审查这份合同",
          "created_at": 1744000000000
        }
      ]
    }
  ]
}
```

**导入规则**：
- 校验 `version` 必须为 `"1.0"`
- 校验 `user_id_hash` 与当前用户匹配（防跨用户导入）
- `session_id` 冲突时，以前缀 `imported_` + 原 ID 重命名，避免覆盖本地会话
- 敏感文件内容**不导出**（仅导出消息文本和元数据）

---

## 技术栈推荐

**推荐栈**：

- **React 18 + TypeScript**——生态最厚、央企招聘容易、长期可维护
- **shadcn/ui**——轻量组件库，可复制粘贴改样式，不绑死任何设计系统
- **TailwindCSS**——样式即类名，UI 改动快
- **EventSource (SSE)**——流式输出标准方案，比 WebSocket 简单
- **Zustand**——轻量状态管理（聊天历史 / 当前会话 / 上传文件）
- **Vite**——构建工具，启动快
- **dexie.js**（**必备**，按 §10.3 分层存储要求）——IndexedDB 包装，存对话历史 + TTL + 可选加密

**如果央企对 UI 一致性有强要求**：

- 把 shadcn/ui 替换为 **Ant Design** 或 **Arco Design**——后者是字节系的设计语言，央企接受度高、组件齐全
- TailwindCSS 仍可保留处理细节样式

**不推荐**：

- Vue + 自研组件——长期维护负债重
- Next.js / Remix——SSR 框架对 SSO + iframe 场景没必要的复杂度
- jQuery / 模板渲染——不要走回头路

---

## 浏览器兼容性与移动端适配

### 浏览器兼容基线

| 浏览器 | 最低版本 | 说明 |
|--------|---------|------|
| Chrome / Edge | 90+ | 完整支持 SSE、IndexedDB、SubtleCrypto |
| Firefox | 88+ | 完整支持 |
| Safari | 14+ | macOS + iOS；注意 Safari 的 IndexedDB 容量限制较严 |
| 国产浏览器（360、搜狗等） | 极速模式（Chromium 90+） | **明确不支持兼容模式（IE 内核）** |

**降级策略**：
- 检测到不支持 EventSource 的浏览器 → 提示"请使用 Chrome/Edge/Firefox/Safari 最新版"
- 检测到不支持 IndexedDB → 降级到 localStorage 存历史（容量受限，仅保留最近 3 条会话）
- 检测到不支持 SubtleCrypto → 加密功能禁用，UI 提示"当前环境不支持本地加密"

### 移动端响应式

widget 需适配以下场景：

| 场景 | 布局调整 |
|------|---------|
| 桌面端（>1024px） | 三栏：侧栏历史列表 + 中区消息流 + 右栏可选信息 |
| 平板（768-1024px） | 侧栏可折叠，消息流占主区域 |
| 手机（<768px） | 单栏全屏；侧栏变为底部抽屉；输入框固定底部 |
| 横屏手机 | 保持单栏，但扩大消息气泡宽度 |

**关键交互调整**：
- 手机端：文件上传按钮从底栏移到输入框左侧的"+"菜单中
- 手机端：快捷指令横向滚动条，而非桌面端的按钮组
- 手机端：长按消息可复制文本（兼容 iOS/Android 原生行为）
- 手机端：顶栏 Agent 下拉改为全屏模态框

## 工程量参考

| 模块 | 工作量 |
|------|--------|
| widget 框架搭建（路由 / SSO 验签 / session 管理） | 3 天 |
| 聊天界面（消息流 / SSE 流式 / 输入框 / 快捷指令） | 3 天 |
| 文件上传 + 进度提示 | 1 天 |
| localStorage 历史 + 导出 / 导入 | 2 天 |
| ui_config 字段动态渲染 | 1 天 |
| 移动端响应式适配 | 2 天 |
| 浏览器兼容性测试与降级 | 1 天 |
| 联调 + bug 修复 | 2 天 |
| **MVP 总计** | **约 15 个工作日（3 周）** |

跟后端 P0 工程量并行，不抢人。

---

## 用户反馈机制（thumbs up / down）

每条模型回复消息旁提供 👍 / 👎 按钮，用户可单选或取消。

### 交互设计

- **展示时机**：消息完整渲染后 1 秒淡入反馈按钮，避免干扰阅读
- **状态**：
  - 未评价 → 空心图标
  - 已评价 → 实心图标 + 记录时间戳
  - 可取消（再次点击同一按钮）
- **扩展反馈**：点 👎 后弹出可选理由（多选）：
  - 回答不准确
  - 没有解决我的问题
  - 格式混乱
  - 引用了错误的制度条文
  - 其他（可输入文字，最多 200 字）

### 数据上报

```json
{
  "session_id": "sess_abc123",
  "message_id": "msg_007",
  "agent_id": "contract-review-agent",
  "run_id": "run_20260507_001",
  "feedback": "thumbs_down",
  "reasons": ["inaccurate", "wrong_citation"],
  "comment": "第 3 条引用的制度已于 2025 年废止",
  "timestamp": "2026-05-07T14:30:00Z"
}
```

### 存储与消费

- **上报方式**：异步 POST `/api/v1/feedback`，不阻塞用户操作
- **服务器端**：写入 `feedback_logs` 表，与 audit_log 按 `run_id` 关联
- **用途**：
  - Agent 质量仪表盘（按 Agent 统计好评率）
  - retention gate 辅助指标（低好评率 Agent 优先体检）
  - 业务部门优化 Skill 的输入

### 隐私边界

- 反馈不含用户对话全文，仅关联 `run_id`
- 用户取消反馈后，服务器同步删除对应记录

---

## SSE 协议规范

Widget 与后端通过 SSE（EventSource）通信，事件类型与数据格式严格定义如下。

### 标准事件类型

| event | 说明 | 数据结构 |
|-------|------|---------|
| `message` | 模型生成的文本 token（流式） | `{ "delta": "...", "finish_reason": null }` |
| `tool_call` | 模型发起工具调用 | `{ "tool_calls": [{ "id": "...", "type": "function", "function": { "name": "...", "arguments": "..." } }] }` |
| `tool_result` | 工具执行结果回传给模型 | `{ "tool_call_id": "...", "role": "tool", "content": "..." }` |
| `checkpoint` | 会话 checkpoint 已保存 | `{ "checkpoint_id": "cp_001", "turn_number": 2 }` |
| `done` | 本轮完成 | `{ "finish_reason": "stop", "usage": { "prompt_tokens": 1200, "completion_tokens": 800 } }` |
| `error` | 错误事件（非致命，可恢复） | `{ "code": "...", "message": "...", "retryable": true/false }` |
| `degradation` | 系统降级通知 | `{ "level": 3, "message": "高峰期降级，模型切换为 qwen3-8b", "since": "2026-05-07T14:30:00Z" }` |
| `timeout` | 模型响应超时 | `{ "code": "MODEL_TIMEOUT", "message": "模型响应超过 60 秒", "retryable": true }` |

### 错误事件代码表

| code | 含义 | retryable | 前端行为 |
|------|------|-----------|---------|
| `SESSION_EXPIRED` | 会话已过期 | false | 自动调用 `/init` 开新会话 |
| `MODEL_TIMEOUT` | 模型响应超时 | true | 提示"响应超时，请重试"，提供重试按钮 |
| `RATE_LIMITED` | 触发限流 | true | 提示"服务繁忙，请稍候"，带倒计时 |
| `TOOL_UNAVAILABLE` | 工具不可用 | true | 提示"部分工具暂不可用，回答可能不完整" |
| `SCHEMA_VALIDATION_FAILED` | 输出 schema 校验失败 | false | 展示原始输出 + 提示"格式异常，已记录" |
| `MAX_TURNS_REACHED` | 达到最大轮数 | false | 提示"本轮对话已达上限，请开新会话" |
| `RUNSPEC_VERSION_MISMATCH` | RunSpec 版本不匹配 | false | 强制刷新页面，重新编译 RunSpec |
| `INTERNAL_ERROR` | 内部错误 | true | 提示"系统异常，请稍后重试" |

### SSE 连接生命周期

```
POST /api/v1/agents/{agent_id}/chat
Content-Type: application/json
Cookie: session=xxx

Body: { "message": "...", "session_id": "..." }

---
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

event: message
data: {"delta":"您好","finish_reason":null}

event: tool_call
data: {"tool_calls":[{"id":"call_001","type":"function","function":{"name":"kb.search","arguments":"{\"query\":\"...\"}"}}]}

event: tool_result
data: {"tool_call_id":"call_001","role":"tool","content":"..."}

event: message
data: {"delta":"根据检索结果","finish_reason":null}

event: done
data: {"finish_reason":"stop","usage":{"prompt_tokens":1200,"completion_tokens":800}}
```

### 降级事件 UI 处理

收到 `degradation` 事件时：

- **Level 1-2**（轻微降级）：顶栏显示黄色预警条"系统繁忙，响应可能变慢"，不影响交互
- **Level 3-4**（中度降级）：顶栏显示橙色预警条"高峰期已切换至低速模型"，输入框旁显示提示图标
- **Level 5-6**（重度降级）：顶栏显示红色预警条"系统负载高，部分功能受限"，禁用文件上传，提示"仅支持文本问答"
- 降级恢复后（收到 `degradation` 事件且 `level=0`），预警条 3 秒后淡出

---

## 文件上传流程

### 完整流程

```
用户点击上传 / 拖拽文件
  ↓
前端预检：文件类型 + 大小（单文件 ≤ 50MB，总并发 ≤ 3 个）
  ↓
POST /api/v1/upload（multipart/form-data，带 session cookie）
  ↓
后端直传 MinIO temp/ 桶 → 返回 file_id
  ↓
前端显示上传进度条（基于 XHR onprogress）
  ↓
上传完成 → 文件以附件形式出现在输入框上方
  ↓
用户发送消息时，file_id 随消息体一起提交
  ↓
模型如需解析 → 调用 doc.extract(file_id)
```

### 前端预检规则

| 检查项 | 规则 | 失败提示 |
|--------|------|---------|
| 文件大小 | 单文件 ≤ 50MB | "文件过大，请拆分为多个文件或联系管理员" |
| 文件类型 | 白名单：pdf, doc, docx, txt, md, xlsx, pptx, png, jpg, jpeg | "不支持该文件格式" |
| 并发数 | 同时上传 ≤ 3 个 | "请等待当前上传完成后再添加" |
| 重复上传 | 同一文件名 + 大小在会话内已存在 → 提示覆盖或重命名 | "该文件已存在，是否覆盖？" |

### 进度条状态

```typescript
interface UploadProgress {
  file_id: string | null;      // 上传完成后赋值
  file_name: string;
  file_size: number;
  status: 'pending' | 'uploading' | 'success' | 'error';
  progress_percent: number;    // 0-100
  error_message?: string;
}
```

---

## 会话恢复与断线重连

### 场景

| 场景 | 期望行为 |
|------|---------|
| 用户刷新页面 | 恢复到当前会话，保留历史消息 |
| 网络断开 30 秒后恢复 | 自动重连 SSE，继续接收流式输出 |
| 网络断开 > 5 分钟 | 提示"会话已过期，请开新会话" |
| 浏览器崩溃后重新打开 | 从 IndexedDB 恢复历史，但需重新 init 会话 |

### 恢复机制

**页面刷新恢复**：

```
widget 加载
  ↓
检查 IndexedDB 中是否存在未完成的 session（status = running）
  ↓
存在 → 调 POST /api/v1/agents/{agent_id}/resume
         Body: { session_id: "sess_abc123", run_id: "run_xxx" }
         后端验证 session 仍有效 → 返回当前 RunSpec + 历史消息摘要
         widget 重渲染消息流
不存在 → 正常走 /init 流程
```

**SSE 断线重连策略**：

```javascript
const es = new EventSource(url);
es.onerror = () => {
  // 浏览器默认 3 秒内自动重连
  // 若连续 3 次重连失败，提示用户手动刷新
};
```

**服务端不缓存 partial output**：
- 模型生成是流式的，服务端**不缓存**已生成的 token 片段
- SSE 断线后，前端重新建立 SSE 连接，服务端**从头开始重新生成**完整回答
- 前端用 checkpoint 中的历史消息作为上下文，重新请求，用户感知为"重新回答"
- 若用户已看到部分输出，前端在重连后先展示 checkpoint 中的最后完整助手消息，再覆盖为新回答
- **敏感文件不恢复**：刷新页面或断线重连后，已上传的合同/公文需重新上传（仅会话内存保留）

**SSE 断线重连**：

```javascript
// 使用 EventSource 的 native 重连 + 自定义逻辑
const es = new EventSource(url);
es.onerror = () => {
  // 3 秒内自动重连（浏览器默认行为）
  // 若连续 3 次重连失败，提示用户手动刷新
};
```

**关键约束**：

- RunSpec 不可变，刷新页面后**不重新编译**，复用原有 `run_id`
- 若 session 已超时（> 30 分钟无活动），后端返回 `SESSION_EXPIRED`，widget 自动调用 `/init` 开新会话
- 敏感文件（上传的合同/公文）**不恢复**——刷新后需重新上传

---

## 为什么不用 iframe

不用 iframe 嵌入 portal，而是独立子站 + 新 tab，原因：

1. **跨域 cookie 隔离**：widget 与 portal 不同 origin，iframe 内嵌会导致 session cookie 的 SameSite 策略复杂化
2. **界面独占性**：聊天 widget 需要完整的页面空间，iframe 内嵌体验差（滚动条嵌套、高度自适应困难）
3. **localStorage 隔离**：iframe 共享父页面的 storage，不同 Agent 的数据可能互相污染
4. **安全策略独立**：widget 需要严格的 CSP、Referrer-Policy，iframe 内嵌会受 portal 安全策略制约

**结论**：独立子站（agent.company.com）是更干净、更安全、体验更好的方案。

## 安全加固

widget 安全 Mitigations 详见 [12-security-audit.md](12-security-audit.md) §widget 安全 Mitigations，本节仅列关键要点：

- widget 加载后**立即从 URL 删除 token**（防浏览器历史泄露）
- Referrer-Policy: no-referrer
- CSP 严格模式 + HTTPS only + HSTS
- token 一次性 jti（防重放）
- 禁用第三方 SDK
- 后端日志自动 mask URL 中的 token 参数
