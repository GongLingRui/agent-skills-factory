import { request } from './client'

export async function exchangeToken(agentId: string, portalJwt: string) {
  return request<{ token: string; expires_at: number; agent_id: string }>(
    '/auth/exchange',
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${portalJwt}` },
      body: JSON.stringify({ agent_id: agentId }),
    },
  )
}

export async function createSession(token: string) {
  return request<{ status: string; session_id: string }>('/auth/session', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

/** Local dev only: backend must have APP_ENV=development + DEV_WIDGET_AUTH_BYPASS. */
export async function devBootstrapSession(agentId: string) {
  return request<{ status: string; session_id: string }>('/auth/dev/session', {
    method: 'POST',
    body: JSON.stringify({ agent_id: agentId }),
  })
}

export async function heartbeat() {
  return request<{ status: string }>('/auth/heartbeat', {
    method: 'POST',
  })
}

export async function fetchSessionMe() {
  return request<{
    user_id_hint: string
    department: string
    /** 64-char hex; optional local IndexedDB encryption (docs/11). */
    user_id_hash: string
    /** 门户 JWT 兑换写入；用于前端 RBAC（如运营台入口）。 */
    permissions?: string[]
    /** 服务端展开角色后的能力码列表（docs/51）。 */
    effective_permissions?: string[]
    can_view_product_metrics?: boolean
    rbac?: { permission_cache_seconds?: number }
  }>('/auth/me', {
    method: 'GET',
  })
}
