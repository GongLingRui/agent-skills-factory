import { API_BASE } from '@/config/api'
import { getAdminApiToken } from '@/lib/adminToken'

export async function parseJsonOrThrow(res: Response): Promise<unknown> {
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const e = body as { error?: { message?: string } }
    throw new Error(e.error?.message || `HTTP ${res.status}`)
  }
  return body
}

function bearerHeaders(includeJsonContentType: boolean): HeadersInit {
  const t = getAdminApiToken()
  if (!t) {
    throw new Error('请在侧栏保存 ADMIN_API_TOKEN（用于审计、降级、指标等运维接口）')
  }
  const h: Record<string, string> = { Authorization: `Bearer ${t}` }
  if (includeJsonContentType) {
    h['Content-Type'] = 'application/json'
  }
  return h
}

/** 审计等接口：优先 Cookie；若已保存运维 Token 则附加 Bearer（与 require_audit_reader 对齐）。 */
function auditHeaders(includeJsonContentType: boolean): HeadersInit {
  const h: Record<string, string> = {}
  if (includeJsonContentType) {
    h['Content-Type'] = 'application/json'
  }
  const t = getAdminApiToken()?.trim()
  if (t) {
    h.Authorization = `Bearer ${t}`
  }
  return h
}

export interface AuditLogRow {
  id: string
  run_id: string | null
  session_id: string | null
  timestamp: string
  level: string
  user_id_hash: string | null
  agent_id: string | null
  department: string | null
  tool_calls: unknown
  token_count: number | null
  cost: number | null
  error_code: string | null
  retrieval_ids: unknown
}

export interface AuditSessionRow {
  session_id: string
  agent_id: string | null
  title: string | null
  status: string
  run_status: string | null
  turn_count: number
  total_tokens: number
  created_at: string | null
  last_activity: string | null
  run_id: string | null
}

export interface ProductMetricsSummary {
  start_date: string
  end_date: string
  mau_window_days: number
  mau_rolling_window_start: string
  dau_by_day: Array<{ date: string; distinct_users: number }>
  mau_rolling_distinct_users: number
  new_chat_sessions: number
  new_agents_registered: number
  feedback: {
    thumbs_up: number
    thumbs_down: number
    total: number
    satisfaction_rate: number | null
    participation_vs_sessions: number | null
  }
}

export async function fetchAuditSessions(params: {
  q?: string
  agent_id?: string
  page?: number
  page_size?: number
}) {
  const qs = new URLSearchParams()
  if (params.q?.trim()) qs.set('q', params.q.trim())
  if (params.agent_id?.trim()) qs.set('agent_id', params.agent_id.trim())
  qs.set('page', String(params.page ?? 1))
  qs.set('page_size', String(params.page_size ?? 20))
  const res = await fetch(`${API_BASE}/audit/sessions?${qs}`, {
    credentials: 'include',
    headers: auditHeaders(false),
  })
  return parseJsonOrThrow(res) as Promise<{
    total: number
    page: number
    page_size: number
    sessions: AuditSessionRow[]
  }>
}

export async function fetchAuditSessionTrace(sessionId: string) {
  const res = await fetch(
    `${API_BASE}/audit/sessions/${encodeURIComponent(sessionId)}/trace`,
    {
      credentials: 'include',
      headers: auditHeaders(false),
    },
  )
  return parseJsonOrThrow(res) as Promise<{
    session_id: string
    run_id: string | null
    checkpoints: Array<{
      checkpoint_id: string
      turn_number: number
      timestamp: string | null
      token_count: number | null
      tool_calls_so_far: unknown[]
    }>
  }>
}

export async function fetchAuditLogs(params: {
  agent_id?: string
  level?: string
  page?: number
  page_size?: number
}) {
  const qs = new URLSearchParams()
  if (params.agent_id) qs.set('agent_id', params.agent_id)
  if (params.level) qs.set('level', params.level)
  qs.set('page', String(params.page ?? 1))
  qs.set('page_size', String(params.page_size ?? 25))
  const res = await fetch(`${API_BASE}/audit/logs?${qs}`, {
    credentials: 'include',
    headers: auditHeaders(false),
  })
  const data = (await parseJsonOrThrow(res)) as {
    total: number
    page: number
    page_size: number
    logs: AuditLogRow[]
  }
  return data
}

export async function downloadAuditLogsCsv(extra: Record<string, string>) {
  const qs = new URLSearchParams(extra)
  const res = await fetch(`${API_BASE}/audit/logs/export?${qs}`, {
    credentials: 'include',
    headers: auditHeaders(false),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const e = body as { error?: { message?: string } }
    throw new Error(e.error?.message || `HTTP ${res.status}`)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `audit_logs_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export async function postDegradationLevel(level: number, reason: string) {
  const res = await fetch(`${API_BASE}/admin/degradation/level`, {
    method: 'POST',
    headers: bearerHeaders(true),
    body: JSON.stringify({ level, reason }),
  })
  await parseJsonOrThrow(res)
}

export async function postDegradationRecover() {
  const res = await fetch(`${API_BASE}/admin/degradation/recover`, {
    method: 'POST',
    headers: bearerHeaders(false),
  })
  await parseJsonOrThrow(res)
}

export async function fetchProductMetricsSummary(
  startDate: string,
  endDate: string,
) {
  const qs = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    mau_window_days: '30',
  })
  const res = await fetch(`${API_BASE}/admin/product-metrics/summary?${qs}`, {
    headers: bearerHeaders(false),
  })
  return parseJsonOrThrow(res) as Promise<ProductMetricsSummary>
}

export async function fetchPlatformPolicies() {
  const res = await fetch(`${API_BASE}/policies/platform`, {
    credentials: 'include',
    headers: auditHeaders(false),
  })
  return parseJsonOrThrow(res) as Promise<{ policies: unknown[] }>
}

export async function fetchTokenQuotas() {
  const res = await fetch(`${API_BASE}/admin/token-quotas`, {
    credentials: 'include',
    headers: auditHeaders(false),
  })
  return parseJsonOrThrow(res) as Promise<{ items: unknown[] }>
}

export async function fetchAdminUsers(page = 1) {
  const qs = new URLSearchParams({ page: String(page), page_size: '20' })
  const res = await fetch(`${API_BASE}/admin/users?${qs}`, {
    credentials: 'include',
    headers: auditHeaders(false),
  })
  return parseJsonOrThrow(res) as Promise<{
    items: Array<{
      user_id: string
      name: string
      department: string
      roles: string[]
    }>
    total: number
  }>
}

export async function fetchAdminDepartments() {
  const res = await fetch(`${API_BASE}/admin/departments`, {
    credentials: 'include',
    headers: auditHeaders(false),
  })
  return parseJsonOrThrow(res) as Promise<{ departments: unknown[] }>
}

// ---------- Policies ----------

export async function postPlatformPolicy(body: { id: string; prompt: string; enabled?: boolean }) {
  const res = await fetch(`${API_BASE}/policies/platform`, {
    method: 'POST',
    credentials: 'include',
    headers: auditHeaders(true),
    body: JSON.stringify(body),
  })
  return parseJsonOrThrow(res) as Promise<{ id: string; version: number; enabled: boolean }>
}

export async function putPlatformPolicy(policyId: string, body: { id: string; prompt: string; enabled?: boolean }) {
  const res = await fetch(`${API_BASE}/policies/platform/${encodeURIComponent(policyId)}`, {
    method: 'PUT',
    credentials: 'include',
    headers: auditHeaders(true),
    body: JSON.stringify(body),
  })
  return parseJsonOrThrow(res) as Promise<{ id: string; version: number; enabled: boolean }>
}

export async function fetchOrgPolicies(department: string) {
  const res = await fetch(`${API_BASE}/policies/org/${encodeURIComponent(department)}`, {
    credentials: 'include',
    headers: auditHeaders(false),
  })
  return parseJsonOrThrow(res) as Promise<{ department: string; policies: unknown[] }>
}

export async function postOrgPolicy(body: { id: string; department: string; prompt: string; enabled?: boolean }) {
  const res = await fetch(`${API_BASE}/policies/org`, {
    method: 'POST',
    credentials: 'include',
    headers: auditHeaders(true),
    body: JSON.stringify(body),
  })
  return parseJsonOrThrow(res) as Promise<{ id: string; version: number; enabled: boolean }>
}

export async function putOrgPolicy(policyId: string, body: { id: string; department: string; prompt: string; enabled?: boolean }) {
  const res = await fetch(`${API_BASE}/policies/org/${encodeURIComponent(policyId)}`, {
    method: 'PUT',
    credentials: 'include',
    headers: auditHeaders(true),
    body: JSON.stringify(body),
  })
  return parseJsonOrThrow(res) as Promise<{ id: string; version: number; enabled: boolean }>
}

// ---------- Quotas ----------

export async function putTokenQuota(
  scope: string,
  scopeId: string,
  body: { budget_tokens: number; effective_next_period?: boolean },
) {
  const res = await fetch(
    `${API_BASE}/admin/token-quotas/${encodeURIComponent(scope)}/${encodeURIComponent(scopeId)}`,
    {
      method: 'PUT',
      credentials: 'include',
      headers: auditHeaders(true),
      body: JSON.stringify(body),
    },
  )
  return parseJsonOrThrow(res) as Promise<{
    scope: string
    scope_id: string
    budget_tokens: number
    period: string
    period_start: string
    period_end: string
    effective_next_period: boolean
  }>
}

// ---------- Users ----------

export async function putUserRoles(
  userId: string,
  body: { roles: string[]; reason?: string },
) {
  const res = await fetch(`${API_BASE}/admin/users/${encodeURIComponent(userId)}/roles`, {
    method: 'PUT',
    credentials: 'include',
    headers: auditHeaders(true),
    body: JSON.stringify(body),
  })
  return parseJsonOrThrow(res) as Promise<{ status: string; user_id: string }>
}

// ---------- Agent disable ----------

export async function postAgentDisable(agentId: string, body: { reason: string; duration_minutes: number }) {
  const res = await fetch(`${API_BASE}/admin/agents/${encodeURIComponent(agentId)}/disable`, {
    method: 'POST',
    credentials: 'include',
    headers: auditHeaders(true),
    body: JSON.stringify(body),
  })
  return parseJsonOrThrow(res) as Promise<{ status: string; agent_id: string; expires_at: string }>
}
