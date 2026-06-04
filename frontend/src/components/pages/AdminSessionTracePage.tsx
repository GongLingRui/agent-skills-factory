import { Fragment, useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  fetchAuditSessionTrace,
  fetchAuditSessions,
  type AuditSessionRow,
} from '@/api/adminBearer'
import { JsonDetailTables } from '@/components/admin/JsonDetailTables'

function fmtTime(iso: string | null | undefined) {
  if (!iso) return '—'
  return iso.replace('T', ' ').replace('Z', '').slice(0, 19)
}

export default function AdminSessionTracePage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [sessions, setSessions] = useState<AuditSessionRow[]>([])
  const [total, setTotal] = useState(0)
  const [listLoading, setListLoading] = useState(false)
  const [error, setError] = useState('')

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [traceLoading, setTraceLoading] = useState(false)
  const [checkpoints, setCheckpoints] = useState<
    Array<{
      checkpoint_id: string
      turn_number: number
      timestamp: string | null
      token_count: number | null
      tool_calls_so_far: unknown[]
    }>
  >([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [expandedCpId, setExpandedCpId] = useState<string | null>(null)

  const loadSessions = useCallback(async () => {
    setError('')
    setListLoading(true)
    try {
      const data = await fetchAuditSessions({
        q: search.trim() || undefined,
        page,
        page_size: pageSize,
      })
      setSessions(data.sessions)
      setTotal(data.total)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载会话列表失败')
      setSessions([])
      setTotal(0)
    } finally {
      setListLoading(false)
    }
  }, [search, page, pageSize])

  useEffect(() => {
    void loadSessions()
  }, [loadSessions])

  const loadTrace = async (sessionId: string) => {
    setError('')
    setTraceLoading(true)
    setSelectedId(sessionId)
    setCheckpoints([])
    setSelectedRunId(null)
    setExpandedCpId(null)
    try {
      const data = await fetchAuditSessionTrace(sessionId)
      setSelectedRunId(data.run_id)
      setCheckpoints(data.checkpoints)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载轨迹失败')
      setSelectedId(null)
    } finally {
      setTraceLoading(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="min-h-[100dvh] bg-[var(--widget-bg)] text-slate-900 dark:text-slate-100">
      <header className="sticky top-0 z-10 border-b border-slate-200/80 dark:border-slate-700 bg-[var(--widget-surface)] px-4 py-4">
        <div className="mx-auto max-w-6xl">
          <nav className="text-sm text-slate-500 mb-1">
            <Link to="/admin/agents" className="hover:text-primary-600">
              管理台
            </Link>
            <span className="mx-2">/</span>
            <span>会话轨迹</span>
          </nav>
          <h1 className="text-xl font-bold">会话轨迹</h1>
          <p className="text-sm text-slate-500 mt-1">
            自动展示近期会话，点击可查看对话轮次与工具调用记录；支持按会话 ID 或标题搜索。
          </p>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 space-y-6">
        <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
          <label className="flex-1 block text-sm">
            <span className="text-slate-600 dark:text-slate-400">搜索会话</span>
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              placeholder="输入会话 ID、标题或 Agent 名称…"
              className="mt-1 w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
            />
          </label>
          <button
            type="button"
            disabled={listLoading}
            onClick={() => void loadSessions()}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {listLoading ? '加载中…' : '刷新列表'}
          </button>
        </div>

        {error && (
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        )}

        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>
            共 {total} 个会话 · 第 {page} / {totalPages} 页
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1 || listLoading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="px-2 py-1 rounded border disabled:opacity-40"
            >
              上一页
            </button>
            <button
              type="button"
              disabled={page >= totalPages || listLoading}
              onClick={() => setPage((p) => p + 1)}
              className="px-2 py-1 rounded border disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)]">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-600 text-left text-xs text-slate-500">
                <th className="px-3 py-2">会话</th>
                <th className="px-3 py-2">Agent</th>
                <th className="px-3 py-2">状态</th>
                <th className="px-3 py-2">对话轮次</th>
                <th className="px-3 py-2">Token 用量</th>
                <th className="px-3 py-2">最近活动</th>
                <th className="px-3 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr
                  key={s.session_id}
                  className={`border-b border-slate-100 dark:border-slate-700/80 ${
                    selectedId === s.session_id ? 'bg-primary-50/60 dark:bg-primary-950/20' : ''
                  }`}
                >
                  <td className="px-3 py-2 align-top">
                    <div className="font-medium">
                      {s.title || '未命名会话'}
                    </div>
                    <div className="text-xs font-mono text-slate-500 mt-0.5">
                      {s.session_id}
                    </div>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{s.agent_id ?? '—'}</td>
                  <td className="px-3 py-2">{s.status}</td>
                  <td className="px-3 py-2">{s.turn_count}</td>
                  <td className="px-3 py-2">{s.total_tokens.toLocaleString('zh-CN')}</td>
                  <td className="px-3 py-2 whitespace-nowrap text-xs">
                    {fmtTime(s.last_activity || s.created_at)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      disabled={traceLoading && selectedId === s.session_id}
                      onClick={() => void loadTrace(s.session_id)}
                      className="text-xs text-primary-600 hover:underline disabled:opacity-50"
                    >
                      查看轨迹
                    </button>
                  </td>
                </tr>
              ))}
              {!listLoading && sessions.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-8 text-center text-slate-500">
                    暂无会话记录
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {selectedId && (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold">
              轨迹详情
              <span className="ml-2 font-mono text-xs text-slate-500 font-normal">
                {selectedId}
                {selectedRunId ? ` · run ${selectedRunId}` : ''}
              </span>
            </h2>
            {traceLoading && (
              <p className="text-sm text-slate-500">正在加载轨迹…</p>
            )}
            {!traceLoading && (
              <div className="overflow-x-auto rounded-xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)]">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-600 text-left text-xs text-slate-500">
                      <th className="px-3 py-2 w-8" />
                      <th className="px-3 py-2">轮次</th>
                      <th className="px-3 py-2">时间</th>
                      <th className="px-3 py-2">Token</th>
                      <th className="px-3 py-2">工具调用次数</th>
                    </tr>
                  </thead>
                  <tbody>
                    {checkpoints.map((cp) => {
                      const toolCount = Array.isArray(cp.tool_calls_so_far)
                        ? cp.tool_calls_so_far.length
                        : 0
                      const expanded = expandedCpId === cp.checkpoint_id
                      return (
                        <Fragment key={cp.checkpoint_id}>
                          <tr className="border-b border-slate-100 dark:border-slate-700/80">
                            <td className="px-3 py-2">
                              {toolCount > 0 && (
                                <button
                                  type="button"
                                  aria-expanded={expanded}
                                  onClick={() =>
                                    setExpandedCpId((id) =>
                                      id === cp.checkpoint_id
                                        ? null
                                        : cp.checkpoint_id,
                                    )
                                  }
                                  className="text-slate-400 hover:text-primary-600 text-xs"
                                >
                                  {expanded ? '▼' : '▶'}
                                </button>
                              )}
                            </td>
                            <td className="px-3 py-2">第 {cp.turn_number} 轮</td>
                            <td className="px-3 py-2 whitespace-nowrap text-xs">
                              {fmtTime(cp.timestamp)}
                            </td>
                            <td className="px-3 py-2">
                              {cp.token_count?.toLocaleString('zh-CN') ?? '—'}
                            </td>
                            <td className="px-3 py-2">{toolCount}</td>
                          </tr>
                          {expanded && toolCount > 0 && (
                            <tr className="border-b border-slate-100 dark:border-slate-700/80 bg-slate-50/50 dark:bg-slate-900/30">
                              <td colSpan={5} className="px-3 py-3">
                                <JsonDetailTables
                                  data={{ tool_calls_so_far: cp.tool_calls_so_far }}
                                />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      )
                    })}
                    {checkpoints.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                          该会话暂无轨迹记录
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  )
}
