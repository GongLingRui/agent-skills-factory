import { useEffect, useRef, useState } from 'react'
import type { AgentItem } from '@/api/agents'
import { formatRelativeTime } from '@/lib/formatTime'

interface HeaderProps {
  title: string
  avatar?: string
  agents: AgentItem[]
  favoriteIds: string[]
  recentIds: string[]
  recentAt: Record<string, number>
  currentAgentId: string | null
  onSwitchAgent: (id: string) => void
  onToggleFavorite?: () => void
  isFavorite?: boolean
  onMoveFavorite?: (direction: -1 | 1) => void
  userHint?: string
  department?: string
  onOpenHistory?: () => void
  /** 桌面侧栏常驻时隐藏顶栏「历史」（仅小屏显示）。 */
  hideHistoryOnLargeScreen?: boolean
  onCloseWidget?: () => void
  onOpenFavoriteReorder?: () => void
  /** 打开「应用库」汇聚页（/apps）。 */
  onOpenApps?: () => void
  /** 打开 Agent 注册中心运营台（/admin/agents）。 */
  onOpenRegistry?: () => void
  onNewChat?: () => void
  onOpenAbout?: () => void
  onOpenSettings?: () => void
  /** 可选：构建号展示（如 ``import.meta.env``）。 */
  buildLabel?: string
  /** 模型下拉（OpenAI 兼容路由）；无则隐藏。 */
  modelSelect?: {
    value: string
    options: Array<{ value: string; label: string }>
    onChange: (value: string) => void
    disabled?: boolean
    loading?: boolean
  }
}

export default function Header({
  title,
  avatar,
  agents,
  favoriteIds,
  recentIds,
  recentAt,
  currentAgentId,
  onSwitchAgent,
  onToggleFavorite,
  isFavorite,
  onMoveFavorite,
  userHint,
  department,
  onOpenHistory,
  hideHistoryOnLargeScreen,
  onCloseWidget,
  onOpenFavoriteReorder,
  onOpenApps,
  onOpenRegistry,
  onNewChat,
  onOpenAbout,
  onOpenSettings,
  buildLabel,
  modelSelect,
}: HeaderProps) {
  const [agentMenuOpen, setAgentMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!agentMenuOpen) return
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setAgentMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [agentMenuOpen])

  const byId = (id: string) => agents.find((a) => a.id === id)

  const favoriteAgents = favoriteIds
    .map((id) => byId(id))
    .filter((a): a is AgentItem => Boolean(a))

  const recentSorted = [...recentIds]
    .filter((id) => byId(id))
    .sort((a, b) => (recentAt[b] ?? 0) - (recentAt[a] ?? 0))

  const recentAgents = recentSorted
    .map((id) => byId(id))
    .filter((a): a is AgentItem => Boolean(a))

  const recentSet = new Set(recentSorted)
  const otherAgents = agents.filter(
    (a) => !favoriteIds.includes(a.id) && !recentSet.has(a.id),
  )

  const current = currentAgentId ? byId(currentAgentId) : null
  const displayName = current?.name || title

  return (
    <header className="border-b border-slate-200/80 dark:border-slate-700 bg-[var(--widget-surface)]/95 backdrop-blur-md sticky top-0 z-20 shadow-sm">
      <div className="flex items-center justify-between gap-3 px-3 sm:px-4 py-2.5 min-h-[3.25rem]">
        <div className="flex items-center gap-2.5 min-w-0 flex-1" ref={menuRef}>
          {avatar ? (
            <img
              src={avatar}
              alt=""
              className="w-9 h-9 rounded-xl object-cover shrink-0 ring-2 ring-white shadow-md"
            />
          ) : (
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary-600 to-primary-700 text-white flex items-center justify-center text-sm font-bold shrink-0 shadow-md ring-2 ring-white">
              {title[0]}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <h1 className="text-[0.95rem] sm:text-base font-semibold text-slate-900 truncate">
                {title}
              </h1>
              {onToggleFavorite && (
                <button
                  type="button"
                  className="text-amber-500 hover:text-amber-600 shrink-0 p-0.5"
                  onClick={onToggleFavorite}
                  aria-label={isFavorite ? '取消收藏' : '收藏'}
                  title={isFavorite ? '取消收藏' : '收藏'}
                >
                  {isFavorite ? '★' : '☆'}
                </button>
              )}
            </div>
            {(userHint || department) && (
              <p className="text-xs text-slate-500 truncate max-w-[50vw] sm:max-w-xs">
                {userHint}
                {department ? ` · ${department}` : ''}
              </p>
            )}
          </div>

          {agents.length > 0 && (
            <div className="relative shrink-0">
              <button
                type="button"
                onClick={() => setAgentMenuOpen((v) => !v)}
                className="flex items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1.5 text-xs text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 shadow-sm max-w-[10rem] sm:max-w-[14rem]"
                aria-expanded={agentMenuOpen}
                aria-haspopup="listbox"
              >
                <span className="truncate font-medium">{displayName}</span>
                <span className="text-slate-400" aria-hidden>
                  ▾
                </span>
              </button>
              {agentMenuOpen && (
                <div
                  className="absolute right-0 top-full mt-1 w-[min(20rem,calc(100vw-2rem))] max-h-[min(28rem,85vh)] rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 shadow-xl z-50 text-sm flex flex-col overflow-hidden"
                  role="listbox"
                >
                  <div className="overflow-y-auto flex-1 min-h-0 py-1 max-h-[min(22rem,70vh)]">
                    {favoriteAgents.length > 0 && (
                      <div className="px-2 py-1">
                        <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 px-2 py-1">
                          收藏
                        </div>
                        {favoriteAgents.map((a) => (
                          <button
                            key={a.id}
                            type="button"
                            role="option"
                            className={`w-full text-left px-2 py-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 ${
                              a.id === currentAgentId
                                ? 'bg-primary-50 dark:bg-primary-900/40 text-primary-800 dark:text-primary-200'
                                : 'text-slate-800 dark:text-slate-200'
                            }`}
                            onClick={() => {
                              onSwitchAgent(a.id)
                              setAgentMenuOpen(false)
                            }}
                          >
                            {a.name}
                          </button>
                        ))}
                      </div>
                    )}
                    {recentAgents.length > 0 && (
                      <div className="px-2 py-1 border-t border-slate-100 dark:border-slate-600">
                        <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 px-2 py-1">
                          最近
                        </div>
                        {recentAgents.map((a) => {
                          const t = recentAt[a.id]
                          const suffix =
                            t !== undefined ? ` · ${formatRelativeTime(t)}` : ''
                          return (
                            <button
                              key={a.id}
                              type="button"
                              role="option"
                              className={`w-full text-left px-2 py-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 ${
                                a.id === currentAgentId
                                  ? 'bg-primary-50 dark:bg-primary-900/40 text-primary-800 dark:text-primary-200'
                                  : 'text-slate-800 dark:text-slate-200'
                              }`}
                              onClick={() => {
                                onSwitchAgent(a.id)
                                setAgentMenuOpen(false)
                              }}
                            >
                              {a.name}
                              <span className="text-slate-400">{suffix}</span>
                            </button>
                          )
                        })}
                      </div>
                    )}
                    {otherAgents.length > 0 && (
                      <div className="px-2 py-1 border-t border-slate-100 dark:border-slate-600">
                        <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 px-2 py-1">
                          全部
                        </div>
                        {otherAgents.map((a) => (
                          <button
                            key={a.id}
                            type="button"
                            role="option"
                            className={`w-full text-left px-2 py-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 ${
                              a.id === currentAgentId
                                ? 'bg-primary-50 dark:bg-primary-900/40 text-primary-800 dark:text-primary-200'
                                : 'text-slate-800 dark:text-slate-200'
                            }`}
                            onClick={() => {
                              onSwitchAgent(a.id)
                              setAgentMenuOpen(false)
                            }}
                          >
                            {a.name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  {onOpenApps && (
                    <div className="shrink-0 border-t border-slate-100 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-2">
                      <button
                        type="button"
                        className="w-full text-left px-2 py-2 rounded-lg text-sm font-medium text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/30"
                        onClick={() => {
                          onOpenApps()
                          setAgentMenuOpen(false)
                        }}
                      >
                        浏览全部 Agent →
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1 sm:gap-1.5 shrink-0 flex-wrap justify-end">
          {buildLabel && (
            <span className="hidden sm:inline text-[10px] text-slate-400 font-mono max-w-[6rem] truncate">
              {buildLabel}
            </span>
          )}
          {isFavorite && onMoveFavorite && (
            <span className="hidden sm:flex gap-0.5">
              <button
                type="button"
                className="text-xs px-1.5 py-1 border border-slate-200 rounded-lg bg-white hover:bg-slate-50"
                title="收藏上移"
                onClick={() => onMoveFavorite(-1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="text-xs px-1.5 py-1 border border-slate-200 rounded-lg bg-white hover:bg-slate-50"
                title="收藏下移"
                onClick={() => onMoveFavorite(1)}
              >
                ↓
              </button>
            </span>
          )}
          {favoriteIds.length > 0 && onOpenFavoriteReorder && (
            <button
              type="button"
              className="hidden md:inline text-xs px-2 py-1.5 border border-slate-200 rounded-lg bg-white hover:bg-slate-50 text-slate-700"
              onClick={onOpenFavoriteReorder}
            >
              排序收藏
            </button>
          )}
          {onOpenRegistry && (
            <button
              type="button"
              className="text-xs sm:text-sm px-2 sm:px-2.5 py-1.5 rounded-lg border border-indigo-200 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-950/50 text-indigo-800 dark:text-indigo-200 hover:bg-indigo-100 dark:hover:bg-indigo-900/40 font-medium"
              onClick={onOpenRegistry}
            >
              运营台
            </button>
          )}
          {modelSelect && (modelSelect.options.length > 0 || modelSelect.loading) && (
            <label className="flex items-center gap-1.5 shrink-0">
              <span className="hidden sm:inline text-xs text-slate-500 whitespace-nowrap">
                模型
              </span>
              <select
                className="text-xs sm:text-sm max-w-[9rem] sm:max-w-[12rem] rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 px-2 py-1.5 shadow-sm disabled:opacity-50"
                value={modelSelect.value}
                disabled={modelSelect.disabled || modelSelect.loading}
                onChange={(e) => modelSelect.onChange(e.target.value)}
                title="选择 OpenAI 兼容推理路由（新会话生效）"
                aria-label="推理模型"
              >
                {modelSelect.loading ? (
                  <option value="">加载中…</option>
                ) : (
                  modelSelect.options.map((o) => (
                    <option key={o.value || '__default'} value={o.value}>
                      {o.label}
                    </option>
                  ))
                )}
              </select>
            </label>
          )}
          {onOpenApps && (
            <button
              type="button"
              className="text-xs sm:text-sm px-2 sm:px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 font-medium"
              onClick={onOpenApps}
            >
              应用库
            </button>
          )}
          {onNewChat && (
            <button
              type="button"
              className="text-xs sm:text-sm px-2 sm:px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 font-medium"
              onClick={onNewChat}
            >
              新对话
            </button>
          )}
          {onOpenAbout && (
            <button
              type="button"
              className="inline-flex items-center text-xs sm:text-sm px-2 sm:px-2.5 py-1.5 rounded-lg border border-transparent text-slate-600 hover:bg-slate-100"
              onClick={onOpenAbout}
            >
              介绍
            </button>
          )}
          {onOpenSettings && (
            <button
              type="button"
              className="text-xs sm:text-sm px-2 py-1.5 rounded-lg text-slate-600 hover:bg-slate-100"
              onClick={onOpenSettings}
              title="隐私与存储"
              aria-label="隐私与存储设置"
            >
              <span className="sr-only">设置</span>
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </button>
          )}
          {onOpenHistory && (
            <button
              type="button"
              className={`text-xs sm:text-sm px-2 sm:px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-medium ${
                hideHistoryOnLargeScreen ? 'lg:hidden' : ''
              }`}
              onClick={onOpenHistory}
            >
              历史
            </button>
          )}
          {onCloseWidget && (
            <button
              type="button"
              className="text-xs sm:text-sm px-2 sm:px-2.5 py-1.5 rounded-lg bg-slate-900 text-white hover:bg-slate-800 font-medium"
              onClick={onCloseWidget}
            >
              关闭
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
