import { LOCAL_STORAGE_KEYS } from '@/config/constants'

export type ThemeMode = 'light' | 'dark'

/** PRD §10.3 / docs/29：轻偏好（主题）存 localStorage。 */
export function getStoredTheme(): ThemeMode {
  if (typeof localStorage === 'undefined') return 'light'
  return localStorage.getItem(LOCAL_STORAGE_KEYS.THEME) === 'dark'
    ? 'dark'
    : 'light'
}

export function applyTheme(mode: ThemeMode): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  if (mode === 'dark') {
    root.classList.add('dark')
  } else {
    root.classList.remove('dark')
  }
  try {
    localStorage.setItem(LOCAL_STORAGE_KEYS.THEME, mode)
  } catch {
    /* ignore quota */
  }
}

/** 首屏前调用，避免主题闪烁。 */
export function initThemeFromStorage(): void {
  applyTheme(getStoredTheme())
}
