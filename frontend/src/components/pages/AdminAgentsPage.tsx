import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  archiveAgentRegistry,
  listRegistryAgents,
  patchAgentLifecycle,
  postAgentDisable,
  type RegistryAgentRow,
} from '@/api/adminRegistry'

const LIFECYCLE_FILTER = [
  { id: 'all', label: '全部' },
  { id: 'active', label: '运营中' },
  { id: 'cold', label: '冷置' },
  { id: 'archived', label: '已归档' },
] as const

/**
 * 运营台：注册中心全量视图 + 生命周期（与 PRD Agent App 注册中心、§11.5 灰度配合）。
 * 鉴权：会话需 ``agent.admin`` / ``agent.write``，或自动化请求携带 ``ADMIN_API_TOKEN``。
 */
export default function AdminAgentsPage() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<RegistryAgentRow[]>([])
  const [filter, setFilter] = useState<string>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [disableModal, setDisableModal] = useState<{
    open: boolean
    agentId: string
    name: string
    reason: string
    durationMinutes: number
  }>({ open: false, agentId: '', name: '', reason: '', durationMinutes: 60 })

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const list = await listRegistryAgents(
        filter === 'all' ? null : filter,
      )
      setRows(list)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '加载失败'
      setError(msg)
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    void load()
  }, [load])

  const run = async (agentId: string, fn: () => Promise<void>) => {
    setBusyId(agentId)
    setError('')
    try {
      await fn()
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '操作失败')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="min-h-[100dvh] bg-[var(--widget-bg)] text-slate-900 dark:text-slate-100">
      <header className="sticky top-0 z-10 border-b border-slate-200/80 dark:border-slate-700 bg-[var(--widget-surface)]/95 backdrop-blur-md px-4 py-4">
        <div className="mx-auto max-w-6xl flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <nav className="text-sm text-slate-500 dark:text-slate-400 mb-1 flex flex-wrap gap-3">
              <Link to="/apps" className="hover:text-primary-600 dark:hover:text-primary-400">
                应用库
              </Link>
              <button
                type="button"
                className="hover:text-primary-600 dark:hover:text-primary-400 text-left"
                onClick={() => navigate(-1)}
              >
                返回上一页
              </button>
            </nav>
            <h1 className="text-xl font-bold tracking-tight">Agent 注册中心</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              灰度与版本历史仍通过 API{' '}
              <code className="text-xs">POST /agents/&#123;id&#125;/releases</code> 等对接。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {LIFECYCLE_FILTER.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                  filter === f.id
                    ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900'
                    : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">
        {error && (
          <div className="rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/40 px-4 py-3 text-red-800 dark:text-red-200 text-sm mb-4">
            {error}
          </div>
        )}
        {loading && (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-14 rounded-xl bg-slate-200/60 dark:bg-slate-700/40 animate-pulse" />
            ))}
          </div>
        )}
        {!loading && rows.length === 0 && !error && (
          <p className="text-center text-slate-500 py-16">暂无 Agent 记录。</p>
        )}
        {!loading && rows.length > 0 && (
          <div className="overflow-x-auto rounded-2xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)] dark:bg-slate-800/50 shadow-widget">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-600 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  <th className="px-4 py-3 font-semibold">ID / 名称</th>
                  <th className="px-4 py-3 font-semibold">版本</th>
                  <th className="px-4 py-3 font-semibold">状态</th>
                  <th className="px-4 py-3 font-semibold">发布策略</th>
                  <th className="px-4 py-3 font-semibold">更新时间</th>
                  <th className="px-4 py-3 font-semibold text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    className="border-b border-slate-100 dark:border-slate-700/80 hover:bg-slate-50/80 dark:hover:bg-slate-700/30"
                  >
                    <td className="px-4 py-3 align-top">
                      <div className="font-mono text-xs text-slate-500 dark:text-slate-400">
                        {r.id}
                      </div>
                      <div className="font-medium text-slate-900 dark:text-slate-100">{r.name}</div>
                    </td>
                    <td className="px-4 py-3 align-top font-mono text-xs">{r.version}</td>
                    <td className="px-4 py-3 align-top">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          r.lifecycle_state === 'active'
                            ? 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-200'
                            : r.lifecycle_state === 'cold'
                              ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-100'
                              : 'bg-slate-200 dark:bg-slate-600 text-slate-700 dark:text-slate-200'
                        }`}
                      >
                        {r.lifecycle_state}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-top text-xs">{r.release_strategy}</td>
                    <td className="px-4 py-3 align-top text-xs text-slate-500 whitespace-nowrap">
                      {r.updated_at?.replace('T', ' ').slice(0, 19) ?? '—'}
                    </td>
                    <td className="px-4 py-3 align-top text-right">
                      <div className="flex flex-wrap justify-end gap-1">
                        {r.lifecycle_state !== 'active' && (
                          <button
                            type="button"
                            disabled={busyId === r.id}
                            className="text-xs px-2 py-1 rounded-lg border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 disabled:opacity-50"
                            onClick={() =>
                              void run(r.id, () =>
                                patchAgentLifecycle(r.id, 'active'),
                              )
                            }
                          >
                            激活
                          </button>
                        )}
                        {r.lifecycle_state === 'active' && (
                          <button
                            type="button"
                            disabled={busyId === r.id}
                            className="text-xs px-2 py-1 rounded-lg border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 hover:bg-amber-50 dark:hover:bg-amber-900/30 disabled:opacity-50"
                            onClick={() =>
                              void run(r.id, () =>
                                patchAgentLifecycle(r.id, 'cold'),
                              )
                            }
                          >
                            冷置
                          </button>
                        )}
                        {r.lifecycle_state === 'active' && (
                          <button
                            type="button"
                            disabled={busyId === r.id}
                            className="text-xs px-2 py-1 rounded-lg border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-50"
                            onClick={() =>
                              setDisableModal({
                                open: true,
                                agentId: r.id,
                                name: r.name,
                                reason: '',
                                durationMinutes: 60,
                              })
                            }
                          >
                            临时禁用
                          </button>
                        )}
                        {r.lifecycle_state !== 'archived' && (
                          <button
                            type="button"
                            disabled={busyId === r.id}
                            className="text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50"
                            onClick={() =>
                              void run(r.id, () =>
                                archiveAgentRegistry(r.id),
                              )
                            }
                          >
                            下架归档
                          </button>
                        )}
                        <Link
                          to={`/apps/${r.id}`}
                          className="text-xs px-2 py-1 rounded-lg border border-primary-200 dark:border-primary-800 text-primary-700 dark:text-primary-300 hover:bg-primary-50 dark:hover:bg-primary-900/30 inline-block"
                        >
                          打开对话
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {disableModal.open && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
            <div className="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-600 bg-[var(--widget-surface)] dark:bg-slate-800 p-6 shadow-lg">
              <h2 className="text-lg font-bold mb-1">临时禁用 Agent</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
                {disableModal.name}（{disableModal.agentId}）
              </p>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
                    原因
                  </label>
                  <input
                    type="text"
                    value={disableModal.reason}
                    onChange={(e) =>
                      setDisableModal((m) => ({ ...m, reason: e.target.value }))
                    }
                    className="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                    placeholder="例如：安全审计、紧急修复"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
                    时长（分钟）
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={disableModal.durationMinutes}
                    onChange={(e) =>
                      setDisableModal((m) => ({
                        ...m,
                        durationMinutes: Math.max(1, parseInt(e.target.value || '1', 10)),
                      }))
                    }
                    className="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>
              <div className="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setDisableModal((m) => ({ ...m, open: false }))}
                  className="rounded-lg px-3 py-2 text-sm font-medium border border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700"
                >
                  取消
                </button>
                <button
                  type="button"
                  disabled={busyId === disableModal.agentId || !disableModal.reason.trim()}
                  onClick={() =>
                    void run(disableModal.agentId, () =>
                      postAgentDisable(disableModal.agentId, {
                        reason: disableModal.reason.trim(),
                        duration_minutes: disableModal.durationMinutes,
                      }).then(() => setDisableModal((m) => ({ ...m, open: false }))),
                    )
                  }
                  className="rounded-lg px-3 py-2 text-sm font-medium bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
                >
                  确认禁用
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
