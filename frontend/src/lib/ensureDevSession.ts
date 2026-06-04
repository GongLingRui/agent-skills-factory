import { devBootstrapSession, fetchSessionMe } from '@/api/auth'

let inflight: Promise<void> | null = null

function devBypassEnabled(): boolean {
  return import.meta.env.VITE_DEV_WIDGET_AUTH_BYPASS === 'true'
}

function defaultDevAgentId(agentId?: string): string {
  const fromArg = agentId?.trim()
  if (fromArg) return fromArg
  const fromEnv = import.meta.env.VITE_DEV_DEFAULT_AGENT_ID?.trim()
  if (fromEnv) return fromEnv
  return 'demo-agent'
}

/**
 * Local dev: ensure HttpOnly session cookie exists before protected API calls.
 * No-op when VITE_DEV_WIDGET_AUTH_BYPASS is not enabled.
 */
export async function ensureDevSession(agentId?: string): Promise<void> {
  if (!devBypassEnabled()) return
  if (inflight) {
    await inflight
    return
  }
  inflight = (async () => {
    try {
      await fetchSessionMe()
      return
    } catch {
      // missing or expired cookie — bootstrap below
    }
    await devBootstrapSession(defaultDevAgentId(agentId))
  })()
  try {
    await inflight
  } finally {
    inflight = null
  }
}

export function isDevAuthBypassEnabled(): boolean {
  return devBypassEnabled()
}
