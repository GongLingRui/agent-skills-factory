/**
 * Encrypted Dexie rows: optional AES-GCM envelope over title + messages.
 */

import { db, type ChatHistory } from '@/db'
import {
  aesGcmDecryptUtf8,
  aesGcmEncryptUtf8,
  deriveWidgetStorageKey,
} from '@/lib/localCrypto'

export const WIDGET_LOCAL_ENCRYPTION_LS = 'widget_local_encryption_enabled'

export interface SecurePayloadV1 {
  v: 1
  title: string
  messages: Array<{
    id?: string
    role: string
    content: string
    serverMessageId?: string
    toolCalls?: unknown
    blocks?: unknown
  }>
}

let cachedKey: CryptoKey | null = null
let cachedForHash: string | null = null

export function isLocalEncryptionEnabled(): boolean {
  return (
    typeof localStorage !== 'undefined' &&
    localStorage.getItem(WIDGET_LOCAL_ENCRYPTION_LS) === '1'
  )
}

export function setLocalEncryptionEnabled(on: boolean): void {
  if (typeof localStorage === 'undefined') {
    return
  }
  if (on) {
    localStorage.setItem(WIDGET_LOCAL_ENCRYPTION_LS, '1')
  } else {
    localStorage.removeItem(WIDGET_LOCAL_ENCRYPTION_LS)
  }
}

export function clearWidgetCryptoKeyCache(): void {
  cachedKey = null
  cachedForHash = null
}

export async function ensureWidgetCryptoKey(
  userIdHashHex: string,
): Promise<CryptoKey> {
  if (cachedKey && cachedForHash === userIdHashHex) {
    return cachedKey
  }
  const k = await deriveWidgetStorageKey(userIdHashHex)
  cachedKey = k
  cachedForHash = userIdHashHex
  return k
}

export function parseSecurePayload(json: string): SecurePayloadV1 {
  const o = JSON.parse(json) as Partial<SecurePayloadV1>
  if (o.v !== 1 || typeof o.title !== 'string' || !Array.isArray(o.messages)) {
    throw new Error('本地加密载荷格式无效')
  }
  return o as SecurePayloadV1
}

export async function sealHistoryPayload(
  key: CryptoKey,
  title: string,
  messages: SecurePayloadV1['messages'],
): Promise<string> {
  const body: SecurePayloadV1 = { v: 1, title, messages }
  const plain = JSON.stringify(body)
  return aesGcmEncryptUtf8(key, plain)
}

export async function openHistoryPayload(
  key: CryptoKey,
  cipherText: string,
): Promise<SecurePayloadV1> {
  const plain = await aesGcmDecryptUtf8(key, cipherText)
  return parseSecurePayload(plain)
}

const PLACEHOLDER_TITLE = '（本地加密会话）'

export function isEncryptedRow(row: ChatHistory): boolean {
  return typeof row.cipherText === 'string' && row.cipherText.length > 0
}

/**
 * Resolve title/messages for UI; plaintext rows unchanged.
 */
export async function revealChatHistory(
  row: ChatHistory,
  key: CryptoKey | null,
): Promise<ChatHistory> {
  if (!isEncryptedRow(row)) {
    return row
  }
  if (!key) {
    return {
      ...row,
      title: PLACEHOLDER_TITLE,
      messages: [],
    }
  }
  try {
    const p = await openHistoryPayload(key, row.cipherText!)
    return {
      ...row,
      title: p.title,
      messages: p.messages,
    }
  } catch {
    return {
      ...row,
      title: '（无法解密，请确认仍为同一账号且未清除站点数据）',
      messages: [],
    }
  }
}

export async function buildEncryptedChatHistory(
  base: Omit<ChatHistory, 'cipherText' | 'messages' | 'title'>,
  key: CryptoKey,
  title: string,
  messages: SecurePayloadV1['messages'],
): Promise<ChatHistory> {
  const cipherText = await sealHistoryPayload(key, title, messages)
  return {
    ...base,
    title: PLACEHOLDER_TITLE,
    messages: [],
    cipherText,
  }
}

export { PLACEHOLDER_TITLE }

/** Decrypt all rows and drop cipherText (disable encryption). */
export async function migrateAllHistoriesToPlain(
  key: CryptoKey,
): Promise<number> {
  const rows = await db.history.toArray()
  let n = 0
  for (const row of rows) {
    if (!row.cipherText) {
      continue
    }
    try {
      const p = await openHistoryPayload(key, row.cipherText)
      await db.history.put({
        id: row.id,
        agentId: row.agentId,
        sessionId: row.sessionId,
        title: p.title,
        messages: p.messages,
        createdAt: row.createdAt,
        updatedAt: row.updatedAt,
      })
      n += 1
    } catch {
      /* leave row unchanged if decrypt fails */
    }
  }
  return n
}

/** Encrypt plaintext rows in place (enable encryption). */
export async function migrateAllHistoriesToCipher(
  key: CryptoKey,
): Promise<number> {
  const rows = await db.history.toArray()
  let n = 0
  for (const row of rows) {
    if (row.cipherText) {
      continue
    }
    const title = row.title || '对话'
    const messages = row.messages || []
    if (!messages.length && title === '对话') {
      continue
    }
    const cipherText = await sealHistoryPayload(key, title, messages)
    await db.history.put({
      id: row.id,
      agentId: row.agentId,
      sessionId: row.sessionId,
      title: PLACEHOLDER_TITLE,
      messages: [],
      cipherText,
      createdAt: row.createdAt,
      updatedAt: row.updatedAt,
    })
    n += 1
  }
  return n
}
