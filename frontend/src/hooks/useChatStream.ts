import { useCallback, useRef, useState } from 'react'
import { streamChatWithRetry, type SSEEvent } from '@/api/sse'
import { useChatStore } from '@/stores/useChatStore'
import { generateMsgId } from '@/lib/id'

export function useChatStream() {
  const {
    sending,
    messages,
    addMessage,
    appendDelta,
    appendBlock,
    updateBlock,
    appendAssistantToolRunning,
    finishAssistantTool,
    setMessageMeta,
    setSending,
    setMessages,
  } = useChatStore()

  const chatAbortRef = useRef<AbortController | null>(null)
  const reconnectAttemptRef = useRef(0)
  const [connectionState, setConnectionState] = useState<
    'connected' | 'reconnecting' | 'disconnected'
  >('disconnected')

  const handleEvent = useCallback((assistantId: string, evt: SSEEvent) => {
    switch (evt.type) {
      case 'text':
        if (evt.delta) {
          appendDelta(assistantId, evt.delta)
          appendBlock(assistantId, { kind: 'text', text: evt.delta })
        }
        if (evt.message_id) {
          setMessageMeta(assistantId, { serverMessageId: evt.message_id })
        }
        break
      case 'tool_call':
        if (evt.tool_id) {
          appendAssistantToolRunning(assistantId, {
            toolId: evt.tool_id,
            callId: evt.call_id,
          })
          appendBlock(assistantId, {
            kind: 'tool_use',
            toolId: evt.tool_id,
            callId: evt.call_id || '',
            status: 'running',
          })
        }
        break
      case 'tool_result':
        if (evt.tool_id) {
          finishAssistantTool(assistantId, {
            toolId: evt.tool_id,
            callId: evt.call_id,
            preview: evt.preview,
            ok: evt.ok,
            code: evt.code,
          })
          updateBlock(assistantId, evt.call_id || '', {
            status: evt.ok === false ? 'error' : 'done',
            preview: evt.preview,
          })
          appendBlock(assistantId, {
            kind: 'tool_result',
            toolId: evt.tool_id,
            callId: evt.call_id || '',
            content: evt.preview || '',
          })
        }
        break
      case 'done':
        if (evt.message_id) {
          setMessageMeta(assistantId, { serverMessageId: evt.message_id })
        }
        break
    }
  }, [appendDelta, appendBlock, updateBlock, appendAssistantToolRunning, finishAssistantTool, setMessageMeta])

  const handleStop = useCallback(() => {
    chatAbortRef.current?.abort()
  }, [])

  const send = useCallback(
    async (
      agentId: string,
      sessionId: string,
      text: string,
      fileIds: string[],
      onError: (msg: string) => void,
    ) => {
      if (!agentId || !sessionId || sending) return
      setSending(true)
      chatAbortRef.current?.abort()
      const ac = new AbortController()
      chatAbortRef.current = ac
      reconnectAttemptRef.current = 0

      // Snapshot for optimistic-update rollback on non-abort failures
      const snapshotMessages = [...messages]

      const msgId = generateMsgId('msg')
      addMessage({ id: msgId, role: 'user', content: text })
      const assistantId = generateMsgId('asst')
      addMessage({ id: assistantId, role: 'assistant', content: '', blocks: [] })

      try {
        for await (const evt of streamChatWithRetry(
          agentId,
          { message: text, session_id: sessionId, file_ids: fileIds },
          { signal: ac.signal },
          {
            maxRetries: 3,
            onConnectionStateChange: (state) => {
              setConnectionState(state)
            },
            onRetry: (attempt) => {
              reconnectAttemptRef.current = attempt
              // eslint-disable-next-line no-console
              console.warn(`SSE retry attempt ${attempt}`)
            },
          },
        )) {
          handleEvent(assistantId, evt)
        }
        setConnectionState('disconnected')
      } catch (e: unknown) {
        setConnectionState('disconnected')
        const aborted =
          e instanceof Error &&
          (e.name === 'AbortError' || e.message.includes('AbortError'))
        if (aborted) {
          appendDelta(assistantId, '\n\n*[已停止生成]*')
        } else {
          // Roll back optimistic updates (keep user message for UX)
          const rolledBack = snapshotMessages.map((m) => ({ ...m }))
          setMessages(rolledBack)
          const msg = e instanceof Error ? e.message : '发送失败'
          onError(msg)
        }
      } finally {
        if (chatAbortRef.current === ac) {
          chatAbortRef.current = null
        }
        setSending(false)
      }
    },
    [sending, messages, addMessage, appendDelta, setMessages, setSending, handleEvent],
  )

  return { sending, send, handleStop, connectionState, reconnectAttempt: reconnectAttemptRef.current }
}
