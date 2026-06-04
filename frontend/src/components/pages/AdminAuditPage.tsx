import { Fragment, useCallback, useEffect, useState } from 'react'
import { listRegistryAgents } from '@/api/adminRegistry'
import {
  downloadAuditLogsCsv,
  fetchAuditLogs,
  type AuditLogRow,
} from '@/api/adminBearer'
import { JsonDetailTables } from '@/components/admin/JsonDetailTables'

const LEVEL_OPTIONS = [
  { value: '', label: '全部级别' },
  { value: 'minimal', label: '简要（minimal）' },
  { value: 'standard', label: '标准（standard）' },
  { value: 'full', label: '完整（full）' },
]

export default function AdminAuditPage() {
  const [agentId, setAgentId] = useState('')
  const [level, setLevel] = useState('')
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState<AuditLogRow[]>([])
  const [total, setTotal] = useState(0)
  const [pageSize] = useState(25)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [agentOptions, setAgentOptions] = useState<
    Array<{ id: string; name: string }>
  >([])
  const [agentsLoading, setAgentsLoading] = useState(true)
  const [expandedLogKey, setExpandedLogKey] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      setAgentsLoading(true)
      try {
        const agents = await listRegistryAgents(null)
        setAgentOptions(
          agents.map((a) => ({ id: a.id, name: a.name || a.id })),
        )
      } catch {
        setAgentOptions([])
      } finally {
        setAgentsLoading(false)
      }
    })()
  }, [])

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const data = await fetchAuditLogs({
        agent_id: agentId.trim() || undefined,
        level: level.trim() || undefined,
        page,
        page_size: pageSize,
      })
      setRows(data.logs)
      setTotal(data.total)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [agentId, level, page, pageSize])

  useEffect(() => {
    void load()
  }, [load])

  const exportCsv = async () => {
    setError('')
    try {
      const extra: Record<string, string> = { limit: '2000' }
      if (agentId.trim()) extra.agent_id = agentId.trim()
      if (level.trim()) extra.level = level.trim()
      await downloadAuditLogsCsv(extra)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '导出失败')
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const logRowKey = (r: AuditLogRow) => `${r.id}@${r.timestamp}`

  const auditListExcludeKeys = [
    'id',
    'timestamp',
    'agent_id',
    'level',
    'session_id',
    'token_count',
    'error_code',
  ]

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-xl font-bold tracking-tight mb-1">审计查询</h1>
      <p className="text-sm text-slate-500 mb-6">
        查看系统调用记录，可按 Agent 与日志级别筛选，并支持导出 CSV。
      </p>
      {error && (
        <div className="mb-4 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-200">
          {error}
        </div>
      )}
      <div className="flex flex-wrap gap-3 items-end mb-4">
        <label className="flex flex-col text-xs gap-1">
          <span className="text-slate-500">Agent</span>
          <select
            value={agentId}
            onChange={(e) => {
              setAgentId(e.target.value)
              setPage(1)
            }}
            disabled={agentsLoading}
            className="rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-2 py-1.5 text-sm min-w-[220px]"
          >
            <option value="">全部 Agent</option>
            {agentOptions.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}（{a.id}）
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-xs gap-1">
          <span className="text-slate-500">日志级别</span>
          <select
            value={level}
            onChange={(e) => {
              setLevel(e.target.value)
              setPage(1)
            }}
            className="rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-2 py-1.5 text-sm w-40"
          >
            {LEVEL_OPTIONS.map((o) => (
              <option key={o.value || 'all'} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded-lg bg-primary-600 text-white text-sm px-4 py-2 font-medium disabled:opacity-50"
        >
          {loading ? '加载中…' : '刷新'}
        </button>
        <button
          type="button"
          onClick={() => void exportCsv()}
          className="rounded-lg border border-slate-200 dark:border-slate-600 text-sm px-4 py-2"
        >
          导出 CSV
        </button>
      </div>
      <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
        <span>
          共 {total} 条 · 第 {page} / {totalPages} 页
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="px-2 py-1 rounded border disabled:opacity-40"
          >
            上一页
          </button>
          <button
            type="button"
            disabled={page >= totalPages || loading}
            onClick={() => setPage((p) => p + 1)}
            className="px-2 py-1 rounded border disabled:opacity-40"
          >
            下一页
          </button>
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)]">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-600 text-left text-slate-500">
              <th className="px-3 py-2 w-8" />
              <th className="px-3 py-2">时间</th>
              <th className="px-3 py-2">Agent</th>
              <th className="px-3 py-2">级别</th>
              <th className="px-3 py-2">会话 ID</th>
              <th className="px-3 py-2">Token</th>
              <th className="px-3 py-2">错误码</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const rowKey = logRowKey(r)
              const expanded = expandedLogKey === rowKey
              return (
                <Fragment key={rowKey}>
                  <tr className="border-b border-slate-100 dark:border-slate-700/80">
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        aria-expanded={expanded}
                        onClick={() =>
                          setExpandedLogKey((k) => (k === rowKey ? null : rowKey))
                        }
                        className="text-slate-400 hover:text-primary-600 text-xs"
                      >
                        {expanded ? '▼' : '▶'}
                      </button>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {r.timestamp?.replace('T', ' ').slice(0, 19)}
                    </td>
                    <td className="px-3 py-2 font-mono">{r.agent_id ?? '—'}</td>
                    <td className="px-3 py-2">{r.level}</td>
                    <td className="px-3 py-2 font-mono max-w-[160px] truncate">
                      {r.session_id ?? '—'}
                    </td>
                    <td className="px-3 py-2">
                      {r.token_count?.toLocaleString('zh-CN') ?? '—'}
                    </td>
                    <td className="px-3 py-2">{r.error_code ?? '—'}</td>
                  </tr>
                  {expanded && (
                    <tr className="border-b border-slate-100 dark:border-slate-700/80 bg-slate-50/50 dark:bg-slate-900/30">
                      <td colSpan={7} className="px-3 py-3">
                        <JsonDetailTables
                          data={r}
                          excludeKeys={auditListExcludeKeys}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-slate-500">
                  暂无审计记录；请确认侧栏已保存 Token，或调整筛选条件。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
