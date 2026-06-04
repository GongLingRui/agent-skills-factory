/** Relative time for Agent recents (prd.md §4.5.6). */

export function formatRelativeTime(tsMs: number, nowMs = Date.now()): string {
  const s = Math.floor((nowMs - tsMs) / 1000)
  if (s < 10) return '刚刚'
  if (s < 60) return `${s} 秒前`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 48) return `${h} 小时前`
  const d = Math.floor(h / 24)
  return `${d} 天前`
}
