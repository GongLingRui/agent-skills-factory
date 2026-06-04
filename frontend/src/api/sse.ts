import { API_BASE } from '@/config/api'

export interface SSEEvent {
  type:
    | 'text'
    | 'tool_call'
    | 'tool_result'
    | 'done'
    | 'error'
    | 'degradation'
    | 'usage_warning'
  delta?: string
  output?: string
  tool_id?: string
  call_id?: string
  status?: string
  preview?: string
  /** Present on ``tool_result`` when execution failed. */
  ok?: boolean
  schema_valid?: boolean
  message_id?: string
  code?: string
  message?: string
  level?: number
  reason?: string
}

export async function* streamChat(
  agentId: string,
  body: { message: string; session_id: string; file_ids?: string[] },
  options?: { signal?: AbortSignal },
): AsyncGenerator<SSEEvent, void, unknown> {
  const res = await fetch(`${API_BASE}/agents/${agentId}/chat`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: options?.signal,
  })

  if (!res.ok || !res.body) {
    throw new Error(`Chat failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let dataLine = ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        dataLine = line.slice(6)
      }
      if (line === '' && dataLine) {
        try {
          const evt: SSEEvent = JSON.parse(dataLine)
          yield evt
        } catch {
          // ignore malformed lines
        }
        dataLine = ''
      }
    }
  }
}

export interface StreamChatRetryOptions {
  maxRetries?: number
  baseDelayMs?: number
  onRetry?: (attempt: number, err: Error) => void
  onConnectionStateChange?: (state: 'connected' | 'reconnecting' | 'disconnected') => void
}

export async function* streamChatWithRetry(
  agentId: string,
  body: { message: string; session_id: string; file_ids?: string[] },
  options?: { signal?: AbortSignal },
  retryOptions?: StreamChatRetryOptions,
): AsyncGenerator<SSEEvent, void, unknown> {
  const maxRetries = retryOptions?.maxRetries ?? 1
  const baseDelayMs = retryOptions?.baseDelayMs ?? 800
  let lastError: Error | undefined

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const innerOptions: { signal?: AbortSignal } = {}
      if (options?.signal) {
        if (options.signal.aborted) {
          throw new Error('AbortError')
        }
        innerOptions.signal = options.signal
      }
      retryOptions?.onConnectionStateChange?.('connected')
      yield* streamChat(agentId, body, innerOptions)
      return
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err))
      const isNetworkError =
        lastError.message.includes('fetch') ||
        lastError.message.includes('network') ||
        lastError.message.includes('Failed to fetch')
      const isRetryableStatus =
        lastError.message.includes('502') ||
        lastError.message.includes('503') ||
        lastError.message.includes('504')
      const shouldRetry =
        (isNetworkError || isRetryableStatus) && attempt < maxRetries
      if (!shouldRetry) {
        retryOptions?.onConnectionStateChange?.('disconnected')
        throw lastError
      }
      retryOptions?.onConnectionStateChange?.('reconnecting')
      if (retryOptions?.onRetry) {
        retryOptions.onRetry(attempt + 1, lastError)
      }
      const jitter = Math.random() * 300
      const delay = baseDelayMs * 2 ** attempt + jitter
      await new Promise((r) => setTimeout(r, delay))
    }
  }
  retryOptions?.onConnectionStateChange?.('disconnected')
  throw lastError || new Error('streamChat failed')
}
