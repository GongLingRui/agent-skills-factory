import { describe, expect, it } from 'vitest'
import { formatRelativeTime } from './formatTime'

describe('formatRelativeTime', () => {
  it('formats seconds and minutes', () => {
    const now = 1_000_000
    expect(formatRelativeTime(now - 15_000, now)).toContain('秒')
    expect(formatRelativeTime(now - 120_000, now)).toContain('分钟')
  })
})
