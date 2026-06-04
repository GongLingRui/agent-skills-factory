import { useEffect, useState, type ReactNode } from 'react'
import { ensureDevSession, isDevAuthBypassEnabled } from '@/lib/ensureDevSession'

/**
 * Waits for dev session cookie when VITE_DEV_WIDGET_AUTH_BYPASS is enabled,
 * so /apps and /admin can call authenticated APIs on first load.
 */
export default function DevAuthBootstrap({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(!isDevAuthBypassEnabled())

  useEffect(() => {
    if (!isDevAuthBypassEnabled()) return
    let cancelled = false
    void ensureDevSession().finally(() => {
      if (!cancelled) setReady(true)
    })
    return () => {
      cancelled = true
    }
  }, [])

  if (!ready) {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center bg-[var(--widget-bg)] text-slate-500 text-sm">
        正在建立本地开发会话…
      </div>
    )
  }

  return <>{children}</>
}
