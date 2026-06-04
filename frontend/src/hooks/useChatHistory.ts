import { useEffect } from 'react'
import { db } from '@/db/index'
import { useChatStore, type ChatMessage } from '@/stores/useChatStore'
import {
  buildEncryptedChatHistory,
  revealChatHistory,
  isLocalEncryptionEnabled,
} from '@/lib/chatHistorySecure'

export function useChatHistory(
  agentId: string | undefined,
  sessionId: string | null,
  cryptoKey: CryptoKey | null,
) {
  const { messages } = useChatStore()
  const localEncryption = isLocalEncryptionEnabled()

  useEffect(() => {
    if (!agentId || !sessionId || messages.length === 0) return
    void (async () => {
      try {
        if (localEncryption && !cryptoKey) return
        const id = `${agentId}:${sessionId}`
        const existing = await db.history.get(id)
        const title =
          messages.find((m) => m.role === 'user')?.content?.slice(0, 40) ||
          '对话'
        const fullMessages = messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          serverMessageId: m.serverMessageId,
          toolCalls: m.toolCalls,
          blocks: m.blocks,
        }))
        const base = {
          id,
          agentId,
          sessionId,
          createdAt: existing?.createdAt ?? new Date(),
          updatedAt: new Date(),
        }
        if (localEncryption && cryptoKey) {
          const row = await buildEncryptedChatHistory(
            base,
            cryptoKey,
            title,
            fullMessages,
          )
          await db.history.put(row)
        } else {
          await db.history.put({ ...base, title, messages: fullMessages })
        }
      } catch {
        /* Dexie 不可用时忽略 */
      }
    })()
  }, [agentId, sessionId, messages, localEncryption, cryptoKey])

  const loadHistory = async (sid: string): Promise<ChatMessage[]> => {
    if (!agentId) return []
    try {
      const row = await db.history.get(`${agentId}:${sid}`)
      const revealed = row
        ? await revealChatHistory(row, cryptoKey)
        : null
      if (revealed?.messages?.length) {
        return revealed.messages.map((m, i) => ({
          id: m.id || `hist_${sid}_${i}`,
          role: (m.role as ChatMessage['role']) || 'user',
          content: m.content || '',
          serverMessageId: m.serverMessageId as string | undefined,
          toolCalls: m.toolCalls as ChatMessage['toolCalls'],
          blocks: m.blocks as ChatMessage['blocks'],
        }))
      }
    } catch {
      /* ignore */
    }
    return []
  }

  return { loadHistory }
}
