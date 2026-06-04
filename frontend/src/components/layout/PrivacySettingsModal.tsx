import { useEffect, useState } from 'react'
import {
  applyTheme,
  getStoredTheme,
  type ThemeMode,
} from '@/lib/theme'

interface PrivacySettingsModalProps {
  open: boolean
  onClose: () => void
  clearOnExit: boolean
  onToggleClearOnExit: () => void
  localEncryption: boolean
  onToggleLocalEncryption: () => void | Promise<void>
  cryptoUnsupported: boolean
  encryptionKeyPending: boolean
}

/**
 * PRD §10.3 / docs/11：本地存储说明、可选加密、主题等轻偏好。
 */
export default function PrivacySettingsModal({
  open,
  onClose,
  clearOnExit,
  onToggleClearOnExit,
  localEncryption,
  onToggleLocalEncryption,
  cryptoUnsupported,
  encryptionKeyPending,
}: PrivacySettingsModalProps) {
  const [themeMode, setThemeMode] = useState<ThemeMode>('light')

  useEffect(() => {
    if (!open) return
    const id = window.setTimeout(() => setThemeMode(getStoredTheme()), 0)
    return () => clearTimeout(id)
  }, [open])

  if (!open) return null

  const toggleTheme = () => {
    const next: ThemeMode = themeMode === 'light' ? 'dark' : 'light'
    setThemeMode(next)
    applyTheme(next)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] dark:bg-black/60"
        aria-label="关闭"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="privacy-settings-title"
        className="relative w-full max-w-md rounded-2xl border border-slate-200/80 dark:border-slate-600 bg-white dark:bg-slate-800 p-6 shadow-xl"
      >
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h2
              id="privacy-settings-title"
              className="text-lg font-semibold text-slate-900 dark:text-slate-100"
            >
              隐私与显示
            </h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
              对话摘要保存在本机浏览器（约 30 天）。共享或公用电脑请勿存放敏感内容；需要时可导出
              JSON 备份。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-800 dark:text-slate-300"
            aria-label="关闭"
          >
            ✕
          </button>
        </div>
        <div className="space-y-4 text-sm">
          <div className="rounded-xl border border-slate-100 dark:border-slate-600 bg-slate-50/80 dark:bg-slate-900/40 p-3">
            <div className="font-medium text-slate-800 dark:text-slate-200 mb-2">
              外观
            </div>
            <p className="text-slate-500 dark:text-slate-400 text-xs mb-3">
              主题偏好保存在本机（PRD §10.3 轻偏好）。
            </p>
            <div className="flex rounded-lg border border-slate-200 dark:border-slate-600 overflow-hidden">
              <button
                type="button"
                className={`flex-1 py-2 text-xs font-medium ${
                  themeMode === 'light'
                    ? 'bg-primary-600 text-white'
                    : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
                }`}
                onClick={() => {
                  setThemeMode('light')
                  applyTheme('light')
                }}
              >
                浅色
              </button>
              <button
                type="button"
                className={`flex-1 py-2 text-xs font-medium border-l border-slate-200 dark:border-slate-600 ${
                  themeMode === 'dark'
                    ? 'bg-primary-600 text-white'
                    : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
                }`}
                onClick={() => {
                  setThemeMode('dark')
                  applyTheme('dark')
                }}
              >
                深色
              </button>
            </div>
            <button
              type="button"
              className="mt-2 text-xs text-primary-600 dark:text-primary-400 hover:underline"
              onClick={toggleTheme}
            >
              快速切换当前主题
            </button>
          </div>
          <label className="flex items-start gap-3 cursor-pointer rounded-xl border border-slate-100 dark:border-slate-600 bg-slate-50/80 dark:bg-slate-900/40 p-3">
            <input
              type="checkbox"
              className="mt-0.5 rounded border-slate-300 dark:border-slate-500"
              checked={clearOnExit}
              onChange={onToggleClearOnExit}
            />
            <span>
              <span className="font-medium text-slate-800 dark:text-slate-200">
                退出页签时清除本地对话
              </span>
              <span className="block text-slate-500 dark:text-slate-400 mt-0.5">
                关闭或刷新前清除 IndexedDB 中的本会话记录。
              </span>
            </span>
          </label>
          <label
            className={`flex items-start gap-3 rounded-xl border p-3 ${
              cryptoUnsupported
                ? 'cursor-not-allowed border-slate-100 dark:border-slate-600 bg-slate-50 opacity-60 dark:bg-slate-900/40'
                : 'cursor-pointer border-slate-100 dark:border-slate-600 bg-slate-50/80 dark:bg-slate-900/40'
            }`}
          >
            <input
              type="checkbox"
              className="mt-0.5 rounded border-slate-300 dark:border-slate-500"
              checked={localEncryption}
              onChange={() => void onToggleLocalEncryption()}
              disabled={cryptoUnsupported}
            />
            <span>
              <span className="font-medium text-slate-800 dark:text-slate-200">
                启用本地加密
              </span>
              <span className="block text-slate-500 dark:text-slate-400 mt-0.5">
                使用浏览器 SubtleCrypto（AES-GCM）加密本地历史；密钥由账号标识派生。
              </span>
            </span>
          </label>
          {cryptoUnsupported && (
            <p className="text-amber-800 dark:text-amber-200 text-xs rounded-lg bg-amber-50 dark:bg-amber-900/40 px-3 py-2 border border-amber-100 dark:border-amber-800">
              当前环境不支持 Web Crypto，无法启用本地加密。
            </p>
          )}
          {localEncryption && encryptionKeyPending && (
            <p className="text-slate-600 dark:text-slate-400 text-xs">
              正在准备加密密钥…
            </p>
          )}
        </div>
        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  )
}
