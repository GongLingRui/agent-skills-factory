import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listAgents, type AgentItem } from '@/api/agents'
import { fetchSessionMe } from '@/api/auth'
import AgentTagsEditor from '@/components/apps/AgentTagsEditor'
import CreateAppModal from '@/components/apps/CreateAppModal'
import TagFilterBar from '@/components/apps/TagFilterBar'
import {
  collectAgentTags,
  loadExtraTags,
  mergeTagLists,
} from '@/lib/tagVocabulary'

/**
 * 汇聚当前用户可见的全部智能体（GET /agents），卡片式浏览；参考 Studio 类产品的筛选与搜索。
 */
export default function AppsDirectoryPage() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState<AgentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [tagFilter, setTagFilter] = useState<string>('all')
  const [showRegistryLink, setShowRegistryLink] = useState(false)
  const [canCreateApp, setCanCreateApp] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [extraTags, setExtraTags] = useState<string[]>(() => loadExtraTags())

  useEffect(() => {
    void (async () => {
      try {
        const me = await fetchSessionMe()
        const p = me.permissions ?? []
        setShowRegistryLink(
          p.some((x) => x === 'agent.write' || x === 'agent.admin'),
        )
        setCanCreateApp(
          p.some((x) => x === 'agent.write' || x === 'agent.admin'),
        )
      } catch {
        setShowRegistryLink(false)
        setCanCreateApp(false)
      }
    })()
  }, [])

  const reloadAgents = useCallback(() => {
    setLoading(true)
    setError('')
    void listAgents()
      .then((res) => setAgents(res.agents || []))
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : '加载失败')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    reloadAgents()
  }, [reloadAgents, refreshKey])

  const tags = useMemo(
    () => mergeTagLists(collectAgentTags(agents), extraTags),
    [agents, extraTags],
  )

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return agents.filter((a) => {
      if (tagFilter !== 'all' && !(a.tags || []).includes(tagFilter)) {
        return false
      }
      if (!q) return true
      const hay = `${a.name} ${a.description}`.toLowerCase()
      return hay.includes(q)
    })
  }, [agents, query, tagFilter])

  const handleAgentTagsUpdated = useCallback(
    (agentId: string, nextTags: string[]) => {
      setAgents((prev) =>
        prev.map((a) => (a.id === agentId ? { ...a, tags: nextTags } : a)),
      )
    },
    [],
  )

  const handleBulkTagsUpdated = useCallback(
    (updates: Array<{ id: string; tags: string[] }>) => {
      const map = new Map(updates.map((u) => [u.id, u.tags]))
      setAgents((prev) =>
        prev.map((a) =>
          map.has(a.id) ? { ...a, tags: map.get(a.id)! } : a,
        ),
      )
    },
    [],
  )

  const openAgent = (agentId: string) => {
    navigate(`/apps/${agentId}`)
  }

  return (
    <div className="min-h-[100dvh] bg-[var(--widget-bg)] text-slate-900 dark:text-slate-100">
      <header className="sticky top-0 z-10 border-b border-slate-200/80 dark:border-slate-700 bg-[var(--widget-surface)]/95 backdrop-blur-md">
        <div className="mx-auto max-w-6xl px-4 py-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-3 mb-1">
              <button
                type="button"
                onClick={() => navigate(-1)}
                className="text-sm text-slate-500 hover:text-primary-700"
              >
                ← 返回
              </button>
              {showRegistryLink && (
                <button
                  type="button"
                  onClick={() => navigate('/admin/agents')}
                  className="text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
                >
                  运营台
                </button>
              )}
            </div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
              应用库
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              选择智能体进入对话（数据来自门户权限过滤后的列表）
            </p>
          </div>
          <div className="relative w-full sm:w-72">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </span>
            <input
              type="search"
              placeholder="搜索名称或描述…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 pl-9 pr-3 py-2.5 text-sm shadow-inner focus:outline-none focus:ring-2 focus:ring-primary-500/30 dark:text-slate-100"
            />
          </div>
        </div>

        <TagFilterBar
          tags={tags}
          tagFilter={tagFilter}
          onTagFilterChange={setTagFilter}
          canManage={canCreateApp}
          agents={agents}
          extraTags={extraTags}
          onExtraTagsChange={setExtraTags}
          onAgentsTagsChange={handleBulkTagsUpdated}
        />
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">
        {loading && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="h-40 rounded-2xl bg-slate-200/60 animate-pulse" />
            ))}
          </div>
        )}
        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-800 text-sm">
            {error}
          </div>
        )}
        {!loading && !error && filtered.length === 0 && !canCreateApp && (
          <p className="text-center text-slate-500 py-16">没有匹配的智能体，试试其它标签或关键词。</p>
        )}
        {!loading && !error && (canCreateApp || filtered.length > 0) && (
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {canCreateApp && (
              <button
                type="button"
                onClick={() => setCreateOpen(true)}
                className="text-left rounded-2xl border-2 border-dashed border-primary-300/80 dark:border-primary-700/80 bg-primary-50/40 dark:bg-primary-950/20 p-5 min-h-[10rem] flex flex-col items-center justify-center gap-3 hover:border-primary-500 hover:bg-primary-50/70 dark:hover:bg-primary-950/40 transition-all group"
              >
                <div className="w-14 h-14 rounded-xl border-2 border-primary-400/60 dark:border-primary-600 flex items-center justify-center text-3xl font-light text-primary-600 dark:text-primary-400 group-hover:scale-105 transition-transform">
                  +
                </div>
                <div className="text-center">
                  <h2 className="font-semibold text-primary-800 dark:text-primary-200">
                    创建应用
                  </h2>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 leading-snug max-w-[14rem]">
                    输入需求；无匹配 Skill 时自动创建
                  </p>
                </div>
              </button>
            )}
            {filtered.map((a) => (
              <div
                key={a.id}
                role="button"
                tabIndex={0}
                onClick={() => openAgent(a.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    openAgent(a.id)
                  }
                }}
                className="text-left rounded-2xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)] dark:bg-slate-800/80 p-5 shadow-widget hover:shadow-lg hover:border-primary-200/80 dark:hover:border-primary-700 transition-all group cursor-pointer"
              >
                <div className="flex gap-4">
                  {a.avatar ? (
                    <img
                      src={a.avatar}
                      alt=""
                      className="w-14 h-14 rounded-xl object-cover ring-2 ring-slate-100 shrink-0"
                    />
                  ) : (
                    <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-primary-600 to-primary-800 text-white flex items-center justify-center text-lg font-bold shrink-0 ring-2 ring-slate-100">
                      {a.name[0]}
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <h2 className="font-semibold text-slate-900 dark:text-slate-100 group-hover:text-primary-700 truncate">
                      {a.name}
                    </h2>
                    <p className="text-xs text-slate-400 font-mono truncate mt-0.5">{a.id}</p>
                  </div>
                </div>
                <p className="mt-4 text-sm text-slate-600 dark:text-slate-300 line-clamp-3 leading-relaxed">
                  {a.description || '暂无描述'}
                </p>
                <AgentTagsEditor
                  agent={a}
                  canEdit={canCreateApp}
                  onUpdated={handleAgentTagsUpdated}
                />
              </div>
            ))}
          </div>
        )}
      </main>
      <CreateAppModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(agentId) => {
          setCreateOpen(false)
          setRefreshKey((k) => k + 1)
          navigate(`/apps/${agentId}`)
        }}
      />
    </div>
  )
}
