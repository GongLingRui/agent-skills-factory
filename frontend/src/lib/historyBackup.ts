import { db, type ChatHistory } from '@/db'
import { revealChatHistory } from '@/lib/chatHistorySecure'

export const CHAT_HISTORY_TTL_MS = 30 * 24 * 60 * 60 * 1000

export async function purgeExpiredChatHistory(): Promise<number> {
  const boundary = new Date(Date.now() - CHAT_HISTORY_TTL_MS)
  return db.history.where('updatedAt').below(boundary).delete()
}

export async function exportHistoriesJson(
  decryptKey: CryptoKey | null = null,
): Promise<string> {
  const rows = await db.history.toArray()
  const normalized: ChatHistory[] = await Promise.all(
    rows.map(async (r) => {
      const rev = await revealChatHistory(r, decryptKey)
      return {
        id: rev.id,
        agentId: rev.agentId,
        sessionId: rev.sessionId,
        title: rev.title,
        messages: rev.messages,
        createdAt: rev.createdAt,
        updatedAt: rev.updatedAt,
      }
    }),
  )
  return JSON.stringify(
    { version: 1, exportedAt: new Date().toISOString(), rows: normalized },
    null,
    2,
  )
}

export async function importHistoriesJson(raw: string): Promise<number> {
  const data = JSON.parse(raw) as {
    version?: number
    rows?: ChatHistory[]
  }
  if (!Array.isArray(data.rows)) {
    throw new Error('备份格式无效：缺少 rows 数组')
  }
  const rows = data.rows.map((r) => ({
    ...r,
    createdAt: r.createdAt ? new Date(r.createdAt) : new Date(),
    updatedAt: r.updatedAt ? new Date(r.updatedAt) : new Date(),
  }))
  await db.history.bulkPut(rows)
  return rows.length
}
