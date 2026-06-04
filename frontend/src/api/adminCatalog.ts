import { API_BASE } from '@/config/api'
import { getAdminApiToken } from '@/lib/adminToken'

async function parseJsonOrThrow(res: Response): Promise<unknown> {
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const e = body as { error?: { message?: string } }
    throw new Error(e.error?.message || `HTTP ${res.status}`)
  }
  return body
}

/** Cookie 会话 + 可选运维 Bearer（与 adminRegistry 一致）。 */
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

export interface SkillListRow {
  id: string
  version: string
  name: string | null
  description: string | null
  risk_tier: string | null
  status: string
  created_at: string | null
}

export async function listSkillsCatalog(): Promise<SkillListRow[]> {
  const res = await fetch(`${API_BASE}/skills`, {
    credentials: 'include',
    headers: sessionHeaders(false),
  })
  const data = (await parseJsonOrThrow(res)) as { skills: SkillListRow[] }
  return data.skills
}

export async function getSkillCatalog(
  skillId: string,
  version?: string | null,
): Promise<unknown> {
  const qs = version ? `?version=${encodeURIComponent(version)}` : ''
  const res = await fetch(
    `${API_BASE}/skills/${encodeURIComponent(skillId)}${qs}`,
    {
      credentials: 'include',
      headers: sessionHeaders(false),
    },
  )
  return parseJsonOrThrow(res)
}

export interface ToolListRow {
  id: string
  version: string
  name: string | null
  description: string | null
  status: string
  created_at: string | null
}

export async function listToolsCatalog(
  status?: string | null,
): Promise<ToolListRow[]> {
  const qs =
    status && status !== 'active'
      ? `?status=${encodeURIComponent(status)}`
      : ''
  const res = await fetch(`${API_BASE}/tools${qs}`, {
    credentials: 'include',
    headers: sessionHeaders(false),
  })
  const data = (await parseJsonOrThrow(res)) as { tools: ToolListRow[] }
  return data.tools
}

export async function getToolCatalog(toolId: string): Promise<unknown> {
  const res = await fetch(
    `${API_BASE}/tools/${encodeURIComponent(toolId)}`,
    {
      credentials: 'include',
      headers: sessionHeaders(false),
    },
  )
  return parseJsonOrThrow(res)
}

export async function approveTool(toolId: string, note?: string) {
  const res = await fetch(`${API_BASE}/tools/${encodeURIComponent(toolId)}/approve`, {
    method: 'POST',
    credentials: 'include',
    headers: sessionHeaders(true),
    body: JSON.stringify({ note: note || '' }),
  })
  return parseJsonOrThrow(res) as Promise<{ id: string; status: string }>
}

export async function uploadSkillTarGz(file: File, skillId: string, version: string) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('skill_id', skillId)
  fd.append('version', version)
  const res = await fetch(`${API_BASE}/skills/upload`, {
    method: 'POST',
    credentials: 'include',
    headers: sessionHeaders(false), // FormData 不带 Content-Type，让浏览器自动设置 boundary
    body: fd,
  })
  return parseJsonOrThrow(res) as Promise<{ id: string; version: string; status: string }>
}
