import { API_BASE } from '@/config/api'
import { getAdminApiToken } from '@/lib/adminToken'

function sessionHeaders(json: boolean): HeadersInit {
  const h: Record<string, string> = {}
  if (json) {
    h['Content-Type'] = 'application/json'
  }
  const t = getAdminApiToken()?.trim()
  if (t) {
    h.Authorization = `Bearer ${t}`
  }
  return h
}

export interface RegistryAgentRow {
  id: string
  name: string
  description: string
  version: string
  lifecycle_state: string
  owner: string | null
  tags: string[]
  release_strategy: string
  created_at: string | null
  updated_at: string | null
}

async function parseJsonOrThrow(res: Response): Promise<unknown> {
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const e = body as { error?: { message?: string } }
    throw new Error(e.error?.message || `HTTP ${res.status}`)
  }
  return body
}

export async function listRegistryAgents(lifecycleFilter?: string | null) {
  const q =
    lifecycleFilter && lifecycleFilter !== 'all'
      ? `?lifecycle_state=${encodeURIComponent(lifecycleFilter)}`
      : ''
  const res = await fetch(`${API_BASE}/admin/agents${q}`, {
    credentials: 'include',
    headers: sessionHeaders(true),
  })
  const data = (await parseJsonOrThrow(res)) as { agents: RegistryAgentRow[] }
  return data.agents
}

export async function patchAgentLifecycle(
  agentId: string,
  lifecycleState: 'active' | 'cold' | 'archived',
) {
  const res = await fetch(
    `${API_BASE}/admin/agents/${encodeURIComponent(agentId)}/lifecycle`,
    {
      method: 'PATCH',
      credentials: 'include',
      headers: sessionHeaders(true),
      body: JSON.stringify({ lifecycle_state: lifecycleState }),
    },
  )
  await parseJsonOrThrow(res)
}

export async function archiveAgentRegistry(agentId: string) {
  const res = await fetch(
    `${API_BASE}/agents/${encodeURIComponent(agentId)}`,
    {
      method: 'DELETE',
      credentials: 'include',
      headers: sessionHeaders(false),
    },
  )
  await parseJsonOrThrow(res)
}

export async function postAgentDisable(
  agentId: string,
  body: { reason: string; duration_minutes: number },
) {
  const res = await fetch(
    `${API_BASE}/admin/agents/${encodeURIComponent(agentId)}/disable`,
    {
      method: 'POST',
      credentials: 'include',
      headers: sessionHeaders(true),
      body: JSON.stringify(body),
    },
  )
  return parseJsonOrThrow(res) as Promise<{
    status: string
    agent_id: string
    expires_at: string
  }>
}
