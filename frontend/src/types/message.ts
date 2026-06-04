export interface Message {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  createdAt?: string
}

export interface ToolCallInfo {
  toolId: string
  callId: string
  status: 'running' | 'done' | 'error'
  preview?: string
}

export type ContentBlock =
  | { kind: 'text'; text: string }
  | { kind: 'tool_use'; toolId: string; callId: string; status: 'running' | 'done' | 'error'; preview?: string }
  | { kind: 'tool_result'; toolId: string; callId: string; content: string }
  | { kind: 'thinking'; text: string }
