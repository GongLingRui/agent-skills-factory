import { describe, expect, it } from 'vitest'
import { reorderByIndex } from './reorderFavorites'

describe('reorderByIndex', () => {
  it('moves item forward and backward', () => {
    expect(reorderByIndex(['a', 'b', 'c'], 0, 2)).toEqual(['b', 'c', 'a'])
    expect(reorderByIndex(['a', 'b', 'c'], 2, 0)).toEqual(['c', 'a', 'b'])
  })

  it('returns copy when noop', () => {
    const a = ['x', 'y']
    const b = reorderByIndex(a, 1, 1)
    expect(b).toEqual(a)
    expect(b).not.toBe(a)
  })
})
