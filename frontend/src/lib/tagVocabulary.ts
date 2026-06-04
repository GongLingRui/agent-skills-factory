const STORAGE_KEY = 'agent-factory:tag-vocabulary'

export function normalizeTag(raw: string): string | null {
  const s = raw.trim()
  return s.length > 0 ? s : null
}

export function loadExtraTags(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    const out: string[] = []
    const seen = new Set<string>()
    for (const item of parsed) {
      const t = normalizeTag(String(item))
      if (t && !seen.has(t)) {
        seen.add(t)
        out.push(t)
      }
    }
    return out.sort((a, b) => a.localeCompare(b, 'zh-CN'))
  } catch {
    return []
  }
}

export function saveExtraTags(tags: string[]): void {
  const normalized = tags
    .map((t) => normalizeTag(t))
    .filter((t): t is string => Boolean(t))
  const unique = [...new Set(normalized)].sort((a, b) =>
    a.localeCompare(b, 'zh-CN'),
  )
  localStorage.setItem(STORAGE_KEY, JSON.stringify(unique))
}

export function mergeTagLists(
  fromAgents: string[],
  extra: string[],
): string[] {
  const s = new Set<string>()
  for (const t of [...fromAgents, ...extra]) {
    const n = normalizeTag(t)
    if (n) s.add(n)
  }
  return [...s].sort((a, b) => a.localeCompare(b, 'zh-CN'))
}

export function collectAgentTags(
  agents: Array<{ tags?: string[] | null }>,
): string[] {
  const s = new Set<string>()
  for (const a of agents) {
    for (const t of a.tags || []) {
      const n = normalizeTag(t)
      if (n) s.add(n)
    }
  }
  return [...s].sort((a, b) => a.localeCompare(b, 'zh-CN'))
}
