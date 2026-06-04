import { API_BASE } from '@/config/api'
import { getAdminApiToken } from '@/lib/adminToken'

export interface ApiError {
  status: number
  message: string
  code?: string
}

function buildHeaders(extra?: HeadersInit): Record<string, string> {
  const h: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (extra && typeof extra === 'object' && !Array.isArray(extra)) {
    for (const [k, v] of Object.entries(extra as Record<string, string>)) {
      if (v !== undefined && v !== null) {
        h[k] = String(v)
      }
    }
  }
  const t = getAdminApiToken()?.trim()
  if (t && !h.Authorization) {
    h.Authorization = `Bearer ${t}`
  }
  return h
}

class StructuredApiError extends Error {
  status: number
  code?: string
  constructor(status: number, message: string, code?: string) {
    super(message)
    this.name = 'StructuredApiError'
    this.status = status
    this.code = code
  }
}

async function requestWithRetry<T>(
  path: string,
  options?: RequestInit,
  {
    maxRetries = 2,
    baseDelayMs = 500,
    retryableStatuses = [408, 429, 502, 503, 504],
  }: {
    maxRetries?: number
    baseDelayMs?: number
    retryableStatuses?: number[]
  } = {},
): Promise<T> {
  let lastError: Error | undefined
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const merged = { ...options }
      merged.headers = buildHeaders(
        options?.headers as Record<string, string> | undefined,
      )
      const res = await fetch(`${API_BASE}${path}`, {
        credentials: 'include',
        ...merged,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new StructuredApiError(
          res.status,
          body.error?.message || `HTTP ${res.status}`,
          body.error?.code,
        )
      }
      return res.json() as Promise<T>
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err))
      const isRetryable =
        err instanceof StructuredApiError &&
        retryableStatuses.includes(err.status)
      if (!isRetryable || attempt >= maxRetries) {
        throw lastError
      }
      const jitter = Math.random() * 200
      const delay = baseDelayMs * 2 ** attempt + jitter
      await new Promise((r) => setTimeout(r, delay))
    }
  }
  throw lastError || new Error('Request failed')
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  return requestWithRetry<T>(path, options)
}

export { request, requestWithRetry, StructuredApiError }
