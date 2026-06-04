import { API_BASE } from '@/config/api'
import { getAdminApiToken } from '@/lib/adminToken'

function sessionHeaders(): HeadersInit {
  const h: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  const t = getAdminApiToken()?.trim()
  if (t) {
    h.Authorization = `Bearer ${t}`
  }
  return h
}

async function parseJsonOrThrow(res: Response): Promise<unknown> {
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const e = body as { error?: { message?: string } }
    throw new Error(e.error?.message || `HTTP ${res.status}`)
  }
  return body
}

export interface ComposeAgentResult {
  id: string
  name: string
  version: string
  skill_id: string
  skill_version: string
  skill_created?: boolean
  status: string
  planner?: string
  tools_allow?: string[]
}

export interface ToolCatalogPreset {
  id: string
  label: string
  description: string
  tools: string[]
  tools_expanded: string[]
}

export interface ToolCatalogGroupTool {
  id: string
  name: string
  description: string
  implemented: boolean
  available: boolean
}

export interface ToolCatalogResponse {
  groups: Array<{
    id: string
    label: string
    tools: ToolCatalogGroupTool[]
  }>
  presets: ToolCatalogPreset[]
  default_tools: string[]
  default_tools_expanded: string[]
}

export async function fetchStudioToolCatalog(): Promise<ToolCatalogResponse> {
  const res = await fetch(`${API_BASE}/agents/studio/tool-catalog`, {
    credentials: 'include',
    headers: sessionHeaders(),
  })
  return parseJsonOrThrow(res) as Promise<ToolCatalogResponse>
}

/** POST /agents/studio/compose — 根据需求自动匹配 Skill 并创建 Agent。 */
export async function composeAgentFromRequirements(
  requirements: string,
  options?: { toolPreset?: string; toolsAllow?: string[] },
): Promise<ComposeAgentResult> {
  const res = await fetch(`${API_BASE}/agents/studio/compose`, {
    method: 'POST',
    credentials: 'include',
    headers: sessionHeaders(),
    body: JSON.stringify({
      requirements,
      tool_preset: options?.toolPreset ?? null,
      tools_allow: options?.toolsAllow ?? null,
    }),
  })
  return parseJsonOrThrow(res) as Promise<ComposeAgentResult>
}

/** PATCH /agents/{id}/tags — 仅更新应用标签。 */
export async function patchAgentTags(agentId: string, tags: string[]) {
  const res = await fetch(
    `${API_BASE}/agents/${encodeURIComponent(agentId)}/tags`,
    {
      method: 'PATCH',
      credentials: 'include',
      headers: sessionHeaders(),
      body: JSON.stringify({ tags }),
    },
  )
  return parseJsonOrThrow(res) as Promise<{
    id: string
    tags: string[]
    status: string
  }>
}
