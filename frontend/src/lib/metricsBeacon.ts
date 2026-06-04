import { API_BASE } from '@/config/api'

export type FrontendMetricInput = {
  agentId?: string | null
  eventType: string
  durationMs?: number | null
  payload?: Record<string, unknown> | null
}

/** JSON body aligned with POST /api/v1/metrics/frontend (docs/32). */
export function serializeFrontendMetric(input: FrontendMetricInput): string {
  return JSON.stringify({
    agent_id: input.agentId ?? undefined,
    event_type: input.eventType,
    duration_ms: input.durationMs ?? undefined,
    payload: input.payload ?? undefined,
  })
}

/**
 * Sends metrics via navigator.sendBeacon when available (falls back to false).
 * Uses same-origin URL so Vite dev proxy can forward /api.
 */
export function sendFrontendMetricBeacon(input: FrontendMetricInput): boolean {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return false
  }
  const path = `${API_BASE}/metrics/frontend`
  const url =
    path.startsWith('http') ? path : `${window.location.origin}${path}`
  const body = serializeFrontendMetric(input)
  if (navigator.sendBeacon) {
    const blob = new Blob([body], { type: 'application/json' })
    return navigator.sendBeacon(url, blob)
  }
  return false
}
