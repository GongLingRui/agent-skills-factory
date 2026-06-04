import { request } from './client'

export interface AgentItem {
  id: string
  name: string
  avatar?: string
  description: string
  tags: string[]
}

export interface AgentDetail {
  id: string
  name: string
  description: string
  ui_config: Record<string, unknown>
}

export interface DegradationInfo {
  level: number
  reason?: string
  hint?: string
}

export async function listAgents() {
  return request<{ agents: AgentItem[] }>('/agents')
}

export async function getAgent(agentId: string) {
  return request<AgentDetail>(`/agents/${agentId}`)
}

export interface ModelCatalogItem {
  id: string
  provider: string
  endpoint_host: string
  api_model: string
  max_tokens: number
  rpm: number
}

export async function getModelCatalog() {
  return request<{
    models: ModelCatalogItem[]
    aliases: Record<string, string>
    default_model: string
  }>('/agents/catalog/models')
}

export async function initSession(
  agentId: string,
  sessionId?: string,
  options?: { model?: string },
) {
  return request<{
    session_id: string
    run_id: string
    ui_config: Record<string, unknown>
    runtime_model?: string
    available_models?: ModelCatalogItem[]
    model_aliases?: Record<string, string>
    degradation?: DegradationInfo
  }>(`/agents/${agentId}/init`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      ...(options?.model ? { model: options.model } : {}),
    }),
  })
}

export async function resumeSession(agentId: string, sessionId: string, checkpointId?: string) {
  return request<{
    session_id: string
    run_id: string
    status: string
    messages: Array<{ role: string; content: string }>
    turn_count: number
    ui_config: Record<string, unknown>
  }>(`/agents/${agentId}/resume`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, checkpoint_id: checkpointId }),
  })
}

export async function postFeedback(body: {
  session_id: string
  message_id: string
  run_id: string
  agent_id: string
  feedback: 'thumbs_up' | 'thumbs_down'
  reasons?: string[]
  comment?: string
}) {
  return request<{ status: string }>('/feedback', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
