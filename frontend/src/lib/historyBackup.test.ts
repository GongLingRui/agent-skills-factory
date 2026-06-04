import { beforeEach, describe, expect, it, vi } from 'vitest'

const { deleteMock, bulkPutMock } = vi.hoisted(() => ({
  deleteMock: vi.fn(),
  bulkPutMock: vi.fn(),
}))

vi.mock('@/db', () => ({
  db: {
    history: {
      where: vi.fn(() => ({
        below: vi.fn(() => ({
          delete: deleteMock,
        })),
      })),
      bulkPut: bulkPutMock,
    },
  },
}))

vi.mock('@/lib/chatHistorySecure', () => ({
  revealChatHistory: async (r: unknown) => r,
}))

import {
  CHAT_HISTORY_TTL_MS,
  importHistoriesJson,
  purgeExpiredChatHistory,
} from './historyBackup'

describe('CHAT_HISTORY_TTL_MS', () => {
  it('is 30 days in milliseconds (prd §10.3)', () => {
    expect(CHAT_HISTORY_TTL_MS).toBe(30 * 24 * 60 * 60 * 1000)
  })
})

describe('purgeExpiredChatHistory', () => {
  beforeEach(() => {
    deleteMock.mockReset()
    deleteMock.mockResolvedValue(4)
  })

  it('deletes histories with updatedAt below the 30d boundary', async () => {
    const n = await purgeExpiredChatHistory()
    expect(n).toBe(4)
    expect(deleteMock).toHaveBeenCalledTimes(1)
  })
})

describe('importHistoriesJson', () => {
  beforeEach(() => {
    bulkPutMock.mockReset()
    bulkPutMock.mockResolvedValue(undefined)
  })

  it('rejects payload without rows array', async () => {
    await expect(importHistoriesJson('{}')).rejects.toThrow('备份格式无效')
    expect(bulkPutMock).not.toHaveBeenCalled()
  })

  it('bulkPut normalized rows and returns count', async () => {
    const raw = JSON.stringify({
      version: 1,
      rows: [
        {
          id: 'h1',
          agentId: 'a1',
          sessionId: 's1',
          title: 't',
          messages: [],
          createdAt: '2026-01-01T00:00:00.000Z',
          updatedAt: '2026-01-02T00:00:00.000Z',
        },
      ],
    })
    const n = await importHistoriesJson(raw)
    expect(n).toBe(1)
    expect(bulkPutMock).toHaveBeenCalledTimes(1)
    const arg = bulkPutMock.mock.calls[0][0]
    expect(arg).toHaveLength(1)
    expect(arg[0].id).toBe('h1')
  })
})
