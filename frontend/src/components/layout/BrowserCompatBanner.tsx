import { useState } from 'react'

/**
 * docs/11-chat-widget：不支持 IndexedDB 等能力时的降级提示（PRD §10.3）。
 */
export default function BrowserCompatBanner() {
  const [dismissed, setDismissed] = useState(
    () =>
      typeof sessionStorage !== 'undefined' &&
      sessionStorage.getItem('widget_compat_hint_dismissed') === '1',
  )

  const okIndexedDb =
    typeof window !== 'undefined' && typeof window.indexedDB !== 'undefined'

  if (dismissed || okIndexedDb) return null

  const dismiss = () => {
    try {
      sessionStorage.setItem('widget_compat_hint_dismissed', '1')
    } catch {
      /* ignore */
    }
    setDismissed(true)
  }

  return (
    <div className="shrink-0 px-4 py-2 bg-orange-50 text-orange-950 text-xs border-b border-orange-100 flex flex-wrap items-center justify-between gap-2">
      <p>
        当前浏览器无法使用 IndexedDB，本地对话历史将无法可靠保存（仅作有限降级）。建议使用
        Chrome / Edge / Firefox / Safari 最新版。
      </p>
      <button
        type="button"
        className="shrink-0 text-orange-800 underline hover:no-underline"
        onClick={dismiss}
      >
        知道了
      </button>
    </div>
  )
}
