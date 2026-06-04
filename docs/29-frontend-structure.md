# 29. Chat Widget 前端工程结构

> 版本：v0.6 · 2026-05-06

---

## 文档定位（对照 PRD）

本文档给出 **Embeddable Chat Widget** 的工程化拆分，覆盖 [prd.md](../prd.md) **§4.5 用户入口与 Chat Widget**、**§10.3 分层存储**、**§10.5 MAU（服务端元数据，前端间接触发）**、**§10.6 观测性（前端上报）**、**§10.7 JWT 泄露防护**。产品交互与信息架构以 [11-chat-widget.md](11-chat-widget.md) 为准；HTTP 契约以 [19-api-reference.md](19-api-reference.md) 为准。

### PRD → 代码落点速查

| PRD 要点 | 工程落点 |
|----------|----------|
| 独立子站 `agent.company.com`、portal `window.open` 新 tab | `main.tsx` / `App.tsx`、部署与 `VITE_*` |
| URL `?token=` 短 JWT，加载后即删 | `hooks/useAuth.ts`：`history.replaceState` 清 query |
| session cookie 不绑 `agent_id`，顶栏切换不重换 token | `useSessionStore` + `POST .../init` 仅换上下文 |
| GET `/agents`、POST `/agents/{id}/init` 切换 Agent | `api/agents.ts`、`useAgentStore.switchAgent` |
| SSE 流式对话（POST + ReadableStream） | `api/sse.ts` |
| localStorage：收藏 / 最近 / 主题 | `utils/storage.ts` 常量键、`useAgentStore` |
| IndexedDB：对话历史 30 天 TTL、可选加密 | `db/*`、`hooks/useEncryption.ts` |
| 敏感附件仅会话内存 | `utils/sessionMemory.ts` |
| ui_config 驱动标题/欢迎语/快捷指令/附件策略 | `Header`、`QuickActions`、`FileUpload` props |
| 降级提示（§9.3~9.5） | `DegradationBanner` + 后端若在 SSE/`/metrics` 暴露降级状态则订阅 |
| 👍👎 反馈 | `FeedbackButtons` → `POST /feedback` |
| 运维调试导出 JSON | `exportImport.ts`、侧栏入口 |
| 禁用第三方分析 SDK、严格 CSP | `index.html`、Vite 插件、`vite.config.ts` |
| 首屏与体验指标上报 | `navigator.sendBeacon` → `POST /api/v1/metrics/frontend` |

---

## 项目目录结构

```
widget/
├── public/
│   ├── agents/                    # Agent 头像静态资源
│   │   └── contract.png
│   └── favicon.ico
├── src/
│   ├── main.tsx                   # 入口
│   ├── App.tsx                    # 根组件（路由 + 全局错误边界）
│   ├── config/
│   │   ├── api.ts                 # API 基地址、超时配置
│   │   └── constants.ts           # 浏览器兼容基线、TTL 常量
│   ├── api/
│   │   ├── client.ts              # Axios / fetch 封装（含拦截器）
│   │   ├── auth.ts                # /auth/exchange / session / heartbeat
│   │   ├── agents.ts              # /agents/* 接口
│   │   └── sse.ts                 # EventSource 封装（含断线重连）
│   ├── stores/
│   │   ├── useSessionStore.ts     # Zustand：session / run_id / ui_config
│   │   ├── useChatStore.ts        # Zustand：消息流、发送状态、工具调用展示
│   │   ├── useAgentStore.ts       # Zustand：Agent 列表、当前 Agent、收藏/最近
│   │   └── useFileStore.ts        # Zustand：上传文件、解析状态
│   ├── db/
│   │   ├── index.ts               # dexie.js Database 定义
│   │   ├── schema.ts              # IndexedDB 表结构
│   │   └── migrations.ts          # 版本升级迁移
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppLayout.tsx      # 三栏/单栏布局切换（响应式）
│   │   │   ├── Header.tsx         # 顶栏：Agent 名称 + 头像 + 用户 + 切换下拉
│   │   │   ├── Sidebar.tsx        # 侧栏：历史对话列表 + 导出导入
│   │   │   └── InputBar.tsx       # 底栏：输入框 + 发送 + 上传 + 快捷指令
│   │   ├── chat/
│   │   │   ├── MessageList.tsx    # 消息流容器（虚拟滚动）
│   │   │   ├── MessageBubble.tsx  # 单条消息气泡（用户/助手/工具）
│   │   │   ├── ToolCallCard.tsx   # 工具调用展示卡片
│   │   │   ├── StreamingText.tsx  # 流式文本渲染（SSE text delta）
│   │   │   └── FeedbackButtons.tsx# 👍 / 👎 + 理由弹窗
│   │   ├── agent/
│   │   │   ├── AgentSwitcher.tsx  # 顶栏下拉：收藏 + 最近 + 浏览全部
│   │   │   ├── AgentCard.tsx      # Agent 列表卡片
│   │   │   └── QuickActions.tsx   # 快捷指令按钮组
│   │   └── upload/
│   │       ├── FileUpload.tsx     # 文件上传组件（拖拽 + 点击）
│   │       ├── FilePreview.tsx    # 已上传文件预览条
│   │       └── UploadProgress.tsx # 上传进度条
│   ├── hooks/
│   │   ├── useAuth.ts             # SSO 验签、token 管理、session 心跳
│   │   ├── useChat.ts             # chat 接口封装（SSE 订阅、消息追加）
│   │   ├── useResume.ts           # 页面刷新后 resume 逻辑
│   │   ├── useResponsive.ts       # 响应式断点 hook
│   │   └── useEncryption.ts       # SubtleCrypto 加密/解密（可选）
│   ├── utils/
│   │   ├── storage.ts             # localStorage / IndexedDB 封装
│   │   ├── encrypt.ts             # PBKDF2 + AES-GCM 加密工具
│   │   ├── sessionMemory.ts       # 敏感文件会话内存存储（Map）
│   │   ├── exportImport.ts        # 对话历史 JSON 导出/导入
│   │   └── validators.ts          # 文件类型/大小校验
│   └── types/
│       ├── agent.ts               # Agent / ui_config / RunSpec 类型
│       ├── message.ts             # 消息结构（user / assistant / tool）
│       ├── api.ts                 # API 请求/响应类型
│       └── sse.ts                 # SSE 事件类型定义
├── index.html
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
└── package.json
```

---

## 核心组件 Props 详表

### AppLayout

```typescript
interface AppLayoutProps {
  agentId: string;                 // 当前 Agent ID
  children: React.ReactNode;
}

// 响应式行为
// - 桌面端（>1024px）：三栏布局（Sidebar + MessageList + 可选右栏）
// - 平板（768-1024px）：侧栏可折叠
// - 手机（<768px）：单栏全屏，侧栏变底部抽屉
```

### StreamingText

```typescript
interface StreamingTextProps {
  text: string;                    // 当前已接收的完整文本
  isStreaming: boolean;            // 是否仍在流式接收
  speed?: 'normal' | 'fast';       // 打字机效果速度
}
// 实现要点：使用 requestAnimationFrame 做逐字渲染，避免 setState 风暴
```

### ToolCallCard

```typescript
interface ToolCallCardProps {
  toolCallId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  status: 'pending' | 'running' | 'success' | 'error';
  result?: string;
  latencyMs?: number;
}
// 实现要点：pending 状态显示脉冲动画；success 折叠展示结果摘要；error 红色警示
```

### FileUpload

```typescript
interface FileUploadProps {
  accept?: string;                 // 默认: ".pdf,.doc,.docx,.txt,.md,.xlsx,.pptx,.png,.jpg,.jpeg"
  maxSizeMB?: number;              // 默认: 50
  maxConcurrent?: number;          // 默认: 3
  onUpload: (files: UploadProgress[]) => void;
  onError: (error: string) => void;
}
```

### DegradationBanner

```typescript
interface DegradationBannerProps {
  level: number;                   // 0-6，与全局降级等级一致（见 13-concurrency）
  message?: string;
  since?: string;                  // ISO 8601
  onDismiss?: () => void;
}
// 颜色映射：1-2 黄、3-4 橙、5-6 红、0 隐藏；文案需对用户可读（如「系统繁忙，已启用快速模式」）
```

### MessageBubble

```typescript
interface MessageBubbleProps {
  message: ChatMessage;
  showFeedback: boolean;           // 是否显示 👍/👎
  onFeedback: (msgId: string, type: 'up' | 'down', reasons?: string[]) => void;
}

type ChatMessage =
  | { role: 'user'; content: string; attachments?: FilePreview[] }
  | { role: 'assistant'; content: string; message_id: string; schema_valid?: boolean | null }
  | { role: 'tool_call'; tool_id: string; status: 'running' | 'success' | 'error' }
  | { role: 'tool_result'; tool_id: string; result: string };
```

### AgentSwitcher

```typescript
interface AgentSwitcherProps {
  currentAgentId: string;
  favorites: AgentMeta[];          // 收藏列表（localStorage 源）
  recent: RecentAgent[];           // 最近使用（localStorage 源）
  onSwitch: (agentId: string) => void;
}

interface RecentAgent {
  agent_id: string;
  name: string;
  last_used_at: number;            // 时间戳
}
```

---

## Zustand Store 设计

### useSessionStore

```typescript
interface SessionState {
  sessionId: string | null;
  runId: string | null;
  uiConfig: UIConfig | null;
  isResumed: boolean;              // 是否从 checkpoint 恢复

  init: (agentId: string) => Promise<void>;
  resume: (agentId: string, sessionId: string, checkpointId: string) => Promise<void>;
  newSession: (agentId: string) => Promise<void>;
  clear: () => void;
}
```

### useChatStore

```typescript
interface ChatState {
  messages: ChatMessage[];
  status: 'idle' | 'sending' | 'streaming' | 'tool_running' | 'error';
  error: string | null;

  sendMessage: (text: string, fileIds?: string[]) => Promise<void>;
  appendStream: (delta: string) => void;
  finalizeStream: (output: string, schemaValid: boolean | null) => void;
  addToolCall: (toolId: string) => void;
  addToolResult: (toolId: string, result: string) => void;
  clearHistory: () => void;
}
```

### useAgentStore

```typescript
interface AgentState {
  agents: AgentMeta[];             // 服务器拉取的全量列表（有权限的）
  currentAgentId: string;
  favorites: string[];             // 收藏 Agent ID 数组（localStorage）
  recent: RecentAgent[];           // 最近使用（localStorage，最多 10 个）

  loadAgents: () => Promise<void>;
  switchAgent: (agentId: string) => Promise<void>;
  toggleFavorite: (agentId: string) => void;
  recordRecent: (agentId: string) => void;
}
```

### useFileStore

```typescript
interface FileState {
  files: UploadedFile[];           // 当前会话已上传文件
  upload: (file: File) => Promise<string>; // 返回 file_id
  remove: (fileId: string) => void;
}

interface UploadedFile {
  file_id: string;
  name: string;
  size: number;
  status: 'uploading' | 'ready' | 'extracted' | 'error';
}
```

---

## API Client 封装

### 请求拦截器

```typescript
// src/api/client.ts
import axios from 'axios';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30000,
  withCredentials: true,             // 携带 session cookie
});

client.interceptors.request.use((config) => {
  // 自动注入 session cookie（由浏览器管理，此处无需手动设置）
  return config;
});

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      // session 过期，提示用户重新从 portal 进入
      window.location.href = '/error?code=SESSION_EXPIRED';
    }
    return Promise.reject(err);
  }
);
```

### SSE 封装

API 规范定义 `/agents/{agent_id}/chat` 为 **POST**（见 [19-api-reference.md](19-api-reference.md)），请求体携带参数。原生 `EventSource` 仅支持 GET，因此使用 `fetch` + `ReadableStream` 实现 POST SSE：

```typescript
// src/api/sse.ts
export async function createChatStream(
  agentId: string,
  sessionId: string,
  message: string,
  fileIds: string[],
  onEvent: (event: SSEEvent) => void,
  abortController: AbortController
): Promise<void> {
  const response = await fetch(`/api/v1/agents/${agentId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ session_id: sessionId, message, file_ids: fileIds }),
    signal: abortController.signal,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    onEvent({ type: 'error', data: err });
    return;
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEventName = 'message';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop()!; // 保留未完整的最后一行

    let currentData = '';
    for (const line of lines) {
      if (line.startsWith('event:')) {
        currentEventName = line.slice(6).trim();
        continue;
      }
      if (line.startsWith('data:')) {
        currentData += line.slice(5).trim();
        continue;
      }
      if (line.trim() === '' && currentData) {
        // SSE 消息块结束（空行分隔）
        const event = JSON.parse(currentData);
        onEvent({ ...event, eventName: currentEventName });
        if (event.type === 'done' || event.type === 'error') {
          reader.cancel();
          return;
        }
        currentData = '';
        currentEventName = 'message';
      }
    }
  }
}
```

**断线重连策略**：
- `AbortController` 由调用方管理，用户主动取消或页面卸载时中断
- 网络异常（`fetch` 抛错）时，前端根据 `onEvent({ type: 'error' })` 提示用户手动刷新；**不自动重连**，避免重复提交同一消息产生副作用
- 服务端通过 `process_pending` 机制保证同一 session 的后续消息按序处理（见 [08-agent-runner.md](08-agent-runner.md) §Session Lock）

---

## 路由设计

widget 是单页应用（SPA），路由极简：

| 路径 | 组件 | 说明 |
|------|------|------|
| `/apps/:agentId` | `AppLayout` | 主入口，带 token query param |
| `/error` | `ErrorPage` | 错误展示（session 过期、无权限等） |

**无前端路由守卫**：权限校验全部走后端 API，后端返回 403 时 widget 展示错误页。

---

## 分层存储实现

### localStorage（轻偏好）

```typescript
// src/utils/storage.ts
const LS_KEYS = {
  FAVORITES: 'af:favorites',       // string[]
  THEME: 'af:theme',               // 'light' | 'dark'
  UI_SETTINGS: 'af:ui',            // { sidebarCollapsed: boolean }
};
```

### IndexedDB（对话历史）

```typescript
// src/db/schema.ts
import Dexie from 'dexie';

class AgentFactoryDB extends Dexie {
  conversations!: Dexie.Table<Conversation, string>;

  constructor() {
    super('AgentFactoryDB');
    this.version(1).stores({
      conversations: '++id, agent_id, user_id_hash, created_at, updated_at',
    });
  }
}

interface Conversation {
  id: string;                      // 本地自增 ID
  agent_id: string;
  user_id_hash: string;            // 当前用户标识（换用户时不展示）
  session_id: string | null;       // 服务器 session（可能已过期）
  messages: ChatMessage[];
  created_at: number;
  updated_at: number;
  expires_at: number;              // 30 天 TTL
}
```

### 会话内存（敏感文件）

```typescript
// src/utils/sessionMemory.ts
const sessionMemory = new Map<string, ArrayBuffer>();

export function storeFileInMemory(fileId: string, data: ArrayBuffer): void {
  sessionMemory.set(fileId, data);
}

export function getFileFromMemory(fileId: string): ArrayBuffer | undefined {
  return sessionMemory.get(fileId);
}

// 页面刷新后 sessionMemory 清空，敏感文件不恢复
```

### IndexedDB 迁移策略

```typescript
// src/db/migrations.ts
import { AgentFactoryDB } from './schema';

export async function runMigrations(db: AgentFactoryDB): Promise<void> {
  // Dexie 在 constructor 中通过 this.version(n).stores() 自动处理 schema 升级
  // 升级规则：只增不减（保留旧字段），新表/索引在新版本中声明
}

// 版本演进示例
// v1 → v2：增加 conversations 表的 schema_valid 索引（用于按校验状态筛选）
// this.version(2).stores({
//   conversations: '++id, agent_id, user_id_hash, created_at, updated_at, schema_valid',
// });
```

**迁移原则**：
- **只增不减**：已有字段和表不删除，避免旧版本浏览器数据丢失
- **惰性重建**：索引变更由 Dexie 在后台自动完成，不阻塞 UI
- **数据清理**：启动时扫描并删除超过 30 天 TTL 的 conversation 记录
- **兼容性窗口**：支持最近 2 个 schema 版本的数据读取，更早版本提示"请刷新页面以升级"

**启动检查清单**（`App.tsx` mount 时执行）：
1. 检测浏览器是否支持 IndexedDB → 不支持时降级为内存存储 + 关闭本地历史功能
2. 打开数据库连接 → 失败时提示用户检查存储权限
3. 清理过期记录 → 静默执行，不阻塞渲染
4. 校验当前用户 hash → 若与上次不同，清空 `conversations` 表中旧用户数据（防跨用户泄露）
```

---

## 加密实现（可选）

```typescript
// src/utils/encrypt.ts
export async function deriveKey(userIdHash: string, platformSalt: Uint8Array): Promise<CryptoKey> {
  const encoder = new TextEncoder();
  const keyMaterial = await window.crypto.subtle.importKey(
    'raw', encoder.encode(userIdHash), 'PBKDF2', false, ['deriveKey']
  );
  return window.crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: platformSalt, iterations: 100000, hash: 'SHA-256' },
    keyMaterial,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  );
}

export async function encryptData(plaintext: string, key: CryptoKey): Promise<{ iv: string; ciphertext: string }> {
  const iv = window.crypto.getRandomValues(new Uint8Array(12));
  const encoder = new TextEncoder();
  const ciphertext = await window.crypto.subtle.encrypt(
    { name: 'AES-GCM', iv }, key, encoder.encode(plaintext)
  );
  return {
    iv: btoa(String.fromCharCode(...iv)),
    ciphertext: btoa(String.fromCharCode(...new Uint8Array(ciphertext))),
  };
}
```

### 加密 salt 与 IV 的存储策略

加密后的数据必须携带解密所需的元数据，否则用户刷新页面后无法读取历史：

```typescript
// IndexedDB 中存储的加密记录结构
interface EncryptedConversation {
  id: string;
  agent_id: string;
  // 加密参数与密文一并存储
  iv: string;             // base64，AES-GCM 用（12 字节随机值，每次加密独立生成）
  ciphertext: string;     // base64，加密后的消息 JSON
  created_at: number;
}
```

**策略**：

- **key 派生**：`user_id_hash = SHA-256(user_id + platform_salt)` 作为 PBKDF2 密码材料，经固定平台 salt + 100000 次迭代派生 AES-GCM 256 位 key。同一用户在所有会话中派生出相同的 key，换用户后无法解密
- **iv**：每次加密独立生成随机 IV（12 字节），同一 key 加密同一明文也不会产生相同密文
- **iv + ciphertext 一起存入 IndexedDB**，解密时按记录取出 iv 即可
- **key 不存储**：key 在运行时通过 `deriveKey(user_id_hash, platformSalt)` 重新派生；用户清除浏览器数据后 ciphertext 即不可恢复
- **平台 salt**：固定值内置于应用配置，运维如需轮换 salt 版本，需同步提供数据迁移工具

**注意**：加密 key 派生自用户身份标识（`user_id_hash`）+ 固定平台 salt，共享电脑场景下其他用户无法解密。UI 默认不开启加密，开启时显式警告。

---

## 启动与路由流程（对齐 PRD §4.5）

```
加载 /apps/:agentId?token=...
  → 读取 token（若存在）
  → POST /api/v1/auth/session { token } → Set-Cookie
  → history.replaceState 去掉 URL 中的 token（PRD §10.7）
  → GET /api/v1/agents/{agentId} 预拉 ui_config（可选，可与下一步合并）
  → POST /api/v1/agents/{agentId}/init → session_id, run_id, ui_config
  → 写入 useSessionStore；IndexedDB 打开或创建会话线程
  → 若有 checkpoint：POST .../resume（见 hooks/useResume）
  → 渲染布局；启动 heartbeat 定时器（每 5 分钟，可见性 gate）
```

- **关 tab**：不保证服务端立刻回收 session；依赖服务端 TTL + 用户下次走 portal 换新 token。
- **切换 Agent**：不调 `/auth/exchange`；直接 `POST .../{newAgentId}/init`（PRD §4.5.5）。

---

## 安全清单（PRD §10.7，前端职责）

| 措施 | 实现位置 |
|------|----------|
| 加载后立即移除 URL token | `useAuth` `replaceState` |
| Referrer-Policy | **生产环境由 Nginx / 网关下发**；本地可在 `index.html` meta 或插件补强 |
| CSP 严格模式 | `vite` / `index.html` 或反向代理 |
| HTTPS + HSTS | 部署层 |
| 禁用 GA / 字节等第三方 SDK | `package.json` 审计；代码禁止引入 |
| 不在日志打印 token | 开发环境亦不 `console.log` URL |

后端 **access log mask `token=`** 不属于前端仓库，但必须在线上与 [41-nginx-config.md](41-nginx-config.md)、[46-logging-spec.md](46-logging-spec.md) 一致。

---

## 环境变量与构建

| 变量 | 说明 |
|------|------|
| `VITE_API_BASE_URL` | 同源或网关前缀，如 `https://agent.company.com/api/v1`（勿把密钥写进 Vite） |
| `VITE_PLATFORM_SALT` | 仅用于前端派生展示用 hash / 加密 salt 的 **公开盐占位**（真实策略与后端对齐） |
| `VITE_HEARTBEAT_MS` | 默认 `300000`（5min），须与 [19-api-reference.md](19-api-reference.md) `/auth/heartbeat` 一致 |

构建：`pnpm build` → 静态资源部署于独立子域；由 Ingress 注入安全响应头。

---

## 与 MAU / retention（PRD §10.5、§15.1）

前端 **不直接调用** MAU 接口；**每次成功 `/init`（新会话）** 由服务端写入 `agent_usage_log`（hash 用户 + 日粒度）。Widget 侧仅需保证 **不误拦 init**、并在 UI 上对 cold/archived Agent 展示后端返回的错误码（`AGENT_INACTIVE`）。

---

## 测试建议目录

```
widget/
├── tests/
│   ├── unit/                 # 存储、SSE 解析、encrypt 纯函数
│   ├── integration/          # MSW mock API + React Testing Library
│   └── e2e/                  # Playwright：portal→widget URL、token 剥离、一轮对话
```

覆盖要点：**token 一次性**、**IndexedDB TTL**、**切换 Agent 不换 token**、**SSE done/error**。

---

## 相关文档索引

| 主题 | 文档 |
|------|------|
| Widget 产品设计 | [11-chat-widget.md](11-chat-widget.md) |
| API 契约 | [19-api-reference.md](19-api-reference.md) |
| 组件 Props 深度 | [38-frontend-component-design.md](38-frontend-component-design.md) |
| 文件上传与秒传 | [39-file-pipeline-design.md](39-file-pipeline-design.md) |
| 可观测性（前端指标名） | [32-observability-design.md](32-observability-design.md) |
| 与 PRD 口径差异 | [47-prd-alignment.md](47-prd-alignment.md) |
