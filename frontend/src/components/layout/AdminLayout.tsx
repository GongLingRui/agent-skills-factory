import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { fetchSessionMe } from '@/api/auth'
import {
  ADMIN_NAV,
  type AdminMeCaps,
  type AdminNavItem,
  filterAdminNav,
} from '@/lib/adminNav'
import {
  clearAdminApiToken,
  getAdminApiToken,
  setAdminApiToken,
} from '@/lib/adminToken'

export default function AdminLayout() {
  const [tokenInput, setTokenInput] = useState('')
  const [savedHint, setSavedHint] = useState(false)
  const [navItems, setNavItems] = useState<AdminNavItem[]>([])
  const [meCaps, setMeCaps] = useState<AdminMeCaps | null>(null)
  const [navHint, setNavHint] = useState<string | null>(null)

  const bearerActive = useMemo(
    () => Boolean((getAdminApiToken() ?? '').trim()),
    [savedHint, tokenInput],
  )

  const refreshNav = useCallback(async () => {
    const hasBearer = Boolean((getAdminApiToken() ?? '').trim())
    if (hasBearer) {
      setNavItems([...ADMIN_NAV])
      setMeCaps(null)
      setNavHint('已启用 ADMIN_API_TOKEN：显示全部分区（接口仍会做服务端校验）。')
      return
    }
    try {
      const caps = await fetchSessionMe()
      setMeCaps(caps)
      setNavItems(filterAdminNav(caps, false))
      setNavHint(
        caps.effective_permissions?.length
          ? '菜单已按当前会话能力过滤（docs/51 阶段 B）。'
          : '当前会话无可用管理权限；请使用门户登录后带 Cookie 访问，或配置 Bearer。',
      )
    } catch {
      setMeCaps(null)
      setNavItems([])
      setNavHint(
        '无会话 Cookie：请先在 Chat Widget 完成登录，或粘贴 ADMIN_API_TOKEN 后保存。',
      )
    }
  }, [])

  useEffect(() => {
    setTokenInput(getAdminApiToken() ?? '')
  }, [])

  useEffect(() => {
    void refreshNav()
  }, [refreshNav, bearerActive])

  const saveToken = () => {
    const t = tokenInput.trim()
    if (t) {
      setAdminApiToken(t)
    } else {
      clearAdminApiToken()
    }
    setSavedHint(true)
    window.setTimeout(() => setSavedHint(false), 2000)
    void refreshNav()
  }

  return (
    <div className="min-h-[100dvh] flex bg-[var(--widget-bg)] text-slate-900 dark:text-slate-100">
      <aside className="w-56 shrink-0 border-r border-slate-200/80 dark:border-slate-700 bg-[var(--widget-surface)] flex flex-col">
        <div className="p-4 border-b border-slate-200/80 dark:border-slate-700">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            管理台
          </div>
          <p className="text-sm font-medium mt-1">Agent Factory</p>
          <p className="text-[11px] text-slate-500 mt-1 leading-snug">
            与 Chat Widget 分离；支持会话 RBAC 与 Bearer（docs/33、docs/51）。
          </p>
        </div>
        <nav className="flex-1 p-2 space-y-0.5">
          {navItems.length === 0 ? (
            <p className="px-3 py-2 text-xs text-slate-500 leading-snug">
              {navHint ?? '加载导航…'}
            </p>
          ) : (
            navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `block rounded-lg px-3 py-2 text-sm transition-colors ${
                    isActive
                      ? 'bg-primary-600 text-white'
                      : 'text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))
          )}
        </nav>
        {meCaps?.rbac?.permission_cache_seconds != null && !bearerActive && (
          <div className="px-3 pb-1 text-[10px] text-slate-500">
            权限快照建议周期 {meCaps.rbac.permission_cache_seconds}s（见 GET /auth/me）。
          </div>
        )}
        <div className="p-3 border-t border-slate-200/80 dark:border-slate-700 space-y-2">
          <label className="block text-[11px] font-medium text-slate-500">
            ADMIN_API_TOKEN
          </label>
          <input
            type="password"
            autoComplete="off"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="粘贴后保存"
            className="w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-2 py-1.5 text-xs font-mono"
          />
          <div className="flex gap-1">
            <button
              type="button"
              onClick={saveToken}
              className="flex-1 rounded-md bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 text-xs py-1.5 font-medium"
            >
              保存
            </button>
            <button
              type="button"
              onClick={() => {
                clearAdminApiToken()
                setTokenInput('')
                void refreshNav()
              }}
              className="rounded-md border border-slate-200 dark:border-slate-600 text-xs px-2"
            >
              清除
            </button>
          </div>
          {savedHint && (
            <p className="text-[10px] text-emerald-600 dark:text-emerald-400">已写入会话存储</p>
          )}
        </div>
        <div className="p-3 text-[11px]">
          <Link to="/apps" className="text-primary-600 dark:text-primary-400 hover:underline">
            ← 应用库
          </Link>
        </div>
      </aside>
      <div className="flex-1 min-w-0 overflow-auto">
        <Outlet />
      </div>
    </div>
  )
}
