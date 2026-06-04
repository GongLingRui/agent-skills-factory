import { API_BASE } from '@/config/api'

export async function uploadFile(agentId: string, file: File): Promise<{ file_id: string; name: string; size: number }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/agents/${agentId}/upload`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error?.message || `HTTP ${res.status}`)
  }
  return res.json()
}
