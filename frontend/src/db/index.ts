import Dexie, { type Table } from 'dexie'

export interface ChatHistory {
  /** `${agentId}:${sessionId}` */
  id: string
  agentId: string
  sessionId: string
  title: string
  messages: Array<{
    id?: string
    role: string
    content: string
    serverMessageId?: string
    toolCalls?: unknown
    blocks?: unknown
  }>
  createdAt: Date
  updatedAt: Date
  /** AES-GCM envelope (docs/11 §分层存储); plaintext rows omit. */
  cipherText?: string
}

export class WidgetDatabase extends Dexie {
  history!: Table<ChatHistory>

  constructor() {
    super('AgentFactoryWidget')
    this.version(1).stores({
      history: 'id, agentId, sessionId, updatedAt',
    })
    this.version(2).stores({
      history: 'id, agentId, sessionId, updatedAt',
    })
  }
}

export const db = new WidgetDatabase()
