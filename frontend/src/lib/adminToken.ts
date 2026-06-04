const STORAGE_KEY = 'agent_factory_admin_api_token'

export function getAdminApiToken(): string | null {
  if (typeof window === 'undefined') return null
  const raw = sessionStorage.getItem(STORAGE_KEY)
  const t = (raw ?? '').trim()
  return t ? t : null
}

export function setAdminApiToken(token: string): void {
  sessionStorage.setItem(STORAGE_KEY, token.trim())
}

export function clearAdminApiToken(): void {
  sessionStorage.removeItem(STORAGE_KEY)
}
