export type SSEEventType = 'text' | 'tool_call' | 'tool_result' | 'done' | 'error' | 'degradation'

export interface SSEPayload {
  type: SSEEventType
  delta?: string
  output?: string
  tool_id?: string
  call_id?: string
  status?: string
  preview?: string
  schema_valid?: boolean
  message_id?: string
  code?: string
  message?: string
}
