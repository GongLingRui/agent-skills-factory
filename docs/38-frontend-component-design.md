# 38. 前端组件详细设计

> 版本：v0.6 · 2026-05-06

---

## 组件分层架构

```
┌─────────────────────────────────────────┐
│              Page Level                  │
│  ChatPage / AdminPage / ErrorPage        │
├─────────────────────────────────────────┤
│           Layout Level                   │
│  AppLayout / Header / Sidebar / InputBar │
├─────────────────────────────────────────┤
│           Feature Level                  │
│  MessageList / AgentSwitcher / FileUpload│
├─────────────────────────────────────────┤
│           Primitive Level                │
│  Button / Icon / Badge / Spinner / Modal │
└─────────────────────────────────────────┘
```

---

## 核心组件 Props 详表

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
  level: number;                   // 0-6
  message?: string;
  since?: string;                  // ISO 8601
  onDismiss?: () => void;
}
// 颜色映射：1-2 黄、3-4 橙、5-6 红、0 隐藏
```

### MessageBubble

```typescript
interface MessageBubbleProps {
  message: ChatMessage;
  showFeedback: boolean;           // 是否显示 👍/👎
  onFeedback: (msgId: string, type: 'up' | 'down', reasons?: string[]) => void;
}
```

---

## Zustand Store 接口补充

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

---

## 与现有文档的衔接

- **Widget 工程结构** → [29-frontend-structure.md](29-frontend-structure.md)
- **Chat Widget 前端设计** → [11-chat-widget.md](11-chat-widget.md)
- **技术选型** → [15-tech-stack.md](15-tech-stack.md)
