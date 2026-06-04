import { create } from 'zustand'
import type { ContentBlock } from '@/types/message'

export interface AssistantToolCallRow {
  toolId: string
  callId?: string
  status: 'running' | 'done' | 'error'
  preview?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  /** Backend ``message_id`` from SSE ``done`` / ``text`` events (for feedback). */
  serverMessageId?: string
  toolCalls?: AssistantToolCallRow[]
  blocks?: ContentBlock[]
}

interface ChatState {
  messages: ChatMessage[]
  sending: boolean
  addMessage: (msg: ChatMessage) => void
  appendDelta: (id: string, delta: string) => void
  appendBlock: (id: string, block: ContentBlock) => void
  updateBlock: (
    id: string,
    callId: string,
    patch: Partial<Exclude<ContentBlock, { kind: 'thinking' | 'text' }>>,
  ) => void
  appendAssistantToolRunning: (
    id: string,
    row: { toolId: string; callId?: string },
  ) => void
  finishAssistantTool: (
    id: string,
    row: {
      toolId: string
      callId?: string
      preview?: string
      ok?: boolean
      code?: string
    },
  ) => void
  setMessageMeta: (
    id: string,
    meta: Partial<Pick<ChatMessage, 'serverMessageId'>>,
  ) => void
  setSending: (v: boolean) => void
  setMessages: (messages: ChatMessage[]) => void
  reset: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  sending: false,
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  appendDelta: (id, delta) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + delta } : m,
      ),
    })),
  appendBlock: (id, block) =>
    set((state) => ({
      messages: state.messages.map((m) => {
        if (m.id !== id) return m
        const blocks = [...(m.blocks || []), block]
        return { ...m, blocks }
      }),
    })),
  updateBlock: (id, callId, patch) =>
    set((state) => ({
      messages: state.messages.map((m) => {
        if (m.id !== id) return m
        const blocks = (m.blocks || []).map((b) => {
          if (
            (b.kind === 'tool_use' || b.kind === 'tool_result') &&
            b.callId === callId
          ) {
            return { ...b, ...patch } as ContentBlock
          }
          return b
        })
        return { ...m, blocks }
      }),
    })),
  appendAssistantToolRunning: (id, row) =>
    set((state) => ({
      messages: state.messages.map((m) => {
        if (m.id !== id || m.role !== 'assistant') return m
        const prev = m.toolCalls || []
        const last = prev[prev.length - 1]
        if (
          last &&
          last.toolId === row.toolId &&
          last.status === 'running' &&
          (row.callId == null ||
            last.callId == null ||
            String(last.callId) === String(row.callId || ''))
        ) {
          return m
        }
        const toolCalls = [
          ...prev,
          {
            toolId: row.toolId,
            callId: row.callId,
            status: 'running' as const,
          },
        ]
        return { ...m, toolCalls }
      }),
    })),
  finishAssistantTool: (id, row) =>
    set((state) => ({
      messages: state.messages.map((m) => {
        if (m.id !== id || m.role !== 'assistant') return m
        const list = [...(m.toolCalls || [])]
        let idx = -1
        for (let i = list.length - 1; i >= 0; i--) {
          const t = list[i]
          if (
            t.toolId === row.toolId &&
            t.status === 'running' &&
            (!row.callId || !t.callId || t.callId === row.callId)
          ) {
            idx = i
            break
          }
        }
        let err = row.ok === false
        if (!err && row.preview) {
          try {
            const j = JSON.parse(row.preview) as {
              ok?: boolean
              code?: string
            }
            if (j && j.ok === false) err = true
            if (j && typeof j.code === 'string' && j.code.includes('TOOL_')) {
              err = true
            }
          } catch {
            /* ignore */
          }
        }
        const status: AssistantToolCallRow['status'] = err ? 'error' : 'done'
        const next: AssistantToolCallRow = {
          toolId: row.toolId,
          callId: row.callId,
          status,
          preview: row.preview,
        }
        if (idx >= 0) {
          list[idx] = { ...list[idx], ...next }
        } else {
          list.push(next)
        }
        return { ...m, toolCalls: list }
      }),
    })),
  setMessageMeta: (id, meta) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, ...meta } : m,
      ),
    })),
  setSending: (v) => set({ sending: v }),
  setMessages: (messages) => set({ messages }),
  reset: () => set({ messages: [], sending: false }),
}))
