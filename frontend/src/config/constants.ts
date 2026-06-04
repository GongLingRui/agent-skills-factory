export const SESSION_COOKIE_NAME = 'session_id'
export const HEARTBEAT_INTERVAL_MS = 5 * 60 * 1000 // 5 minutes
export const MAX_HEARTBEAT_FAILURES = 3
export const LOCAL_STORAGE_KEYS = {
  FAVORITES: 'af:favorites',
  RECENTS: 'af:recents',
  THEME: 'af:theme',
} as const
export const MAX_RECENTS = 10
/** 收藏数量上限（与最近列表一致，PRD localStorage LRU≤10） */
export const MAX_FAVORITES = 10
