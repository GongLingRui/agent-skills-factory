import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  approveTool,
  getToolCatalog,
  listToolsCatalog,
  type ToolListRow,
} from '@/api/adminCatalog'
import { JsonDetailTables } from '@/components/admin/JsonDetailTables'

export default function AdminToolsPage() {
  const [rows, setRows] = useState<ToolListRow[]>([])
  const [statusFilter, setStatusFilter] = useState<string>('active')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [detailId, setDetailId] = useState<string | null>(null)
  const [detailData, setDetailData] = useState<unknown>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const list = await listToolsCatalog(statusFilter)
      setRows(list)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    void load()
  }, [load])

  const openDetail = async (id: string) => {
    setDetailId(id)
    setDetailData('加载中…')
    try {
      const raw = await getToolCatalog(id)
      setDetailData(raw)
    } catch (e: unknown) {
      setDetailData(e instanceof Error ? e.message : '加载失败')
    }
  }

  const runApprove = async (id: string) => {
    setBusyId(id)
    setError('')
    try {
      await approveTool(id, '管理台审批')
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '审批失败')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="min-h-[100dvh] bg-[var(--widget-bg)] text-slate-900 dark:text-slate-100">
      <header className="sticky top-0 z-10 border-b border-slate-200/80 dark:border-slate-700 bg-[var(--widget-surface)] px-4 py-4">
        <div className="mx-auto max-w-6xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <nav className="text-sm text-slate-500 mb-1">
              <Link to="/admin/agents" className="hover:text-primary-600">
                管理台
              </Link>
              <span className="mx-2">/</span>
              <span>Tool 目录</span>
            </nav>
            <h1 className="text-xl font-bold">Tool 目录</h1>
            <p className="text-sm text-slate-500 mt-1">支持双签审批流程（当 TOOL_DUAL_SIGN_ENABLED 开启时）</p>
          </div>
          <div className="flex gap-2">
            {[
              { id: 'active', label: '已启用' },
              { id: 'pending_approval', label: '待审批' },
              { id: 'disabled', label: '已停用' },
            ].map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setStatusFilter(s.id)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${statusFilter === s.id ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900' : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600'}`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 space-y-4">
        {error && (
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        )}
        {loading ? (
          <p className="text-sm text-slate-500">加载中…</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)]">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-800/80 text-left">
                <tr>
                  <th className="px-4 py-3 font-semibold text-xs uppercase tracking-wide text-slate-500">id</th>
                  <th className="px-4 py-3 font-semibold text-xs uppercase tracking-wide text-slate-500">version</th>
                  <th className="px-4 py-3 font-semibold text-xs uppercase tracking-wide text-slate-500">name</th>
                  <th className="px-4 py-3 font-semibold text-xs uppercase tracking-wide text-slate-500">状态</th>
                  <th className="px-4 py-3 font-semibold text-xs uppercase tracking-wide text-slate-500" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={`${r.id}@${r.version}`}
                    className="border-t border-slate-200 dark:border-slate-700"
                  >
                    <td className="px-4 py-3 font-mono text-xs">{r.id}</td>
                    <td className="px-4 py-3 font-mono text-xs">{r.version}</td>
                    <td className="px-4 py-3">{r.name ?? '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${r.status === 'active' ? 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-200' : r.status === 'pending_approval' ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-100' : 'bg-slate-200 dark:bg-slate-600 text-slate-700 dark:text-slate-200'}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex flex-wrap justify-end gap-1">
                        {r.status === 'pending_approval' && (
                          <button
                            type="button"
                            disabled={busyId === r.id}
                            className="text-xs px-2 py-1 rounded-lg border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 disabled:opacity-50"
                            onClick={() => void runApprove(r.id)}
                          >
                            审批通过
                          </button>
                        )}
                        <button
                          type="button"
                          className="text-primary-600 dark:text-primary-400 text-xs hover:underline"
                          onClick={() => void openDetail(r.id)}
                        >
                          查看详情
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!loading && rows.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-500">暂无数据</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        {detailId && (
          <div className="rounded-xl border border-slate-200 dark:border-slate-700 p-4 space-y-2 bg-[var(--widget-surface)]">
            <div className="flex justify-between items-center gap-2">
              <p className="text-sm font-medium">
                详情 <code className="text-xs">{detailId}</code>
              </p>
              <button
                type="button"
                className="text-xs text-slate-500 hover:text-slate-800"
                onClick={() => {
                  setDetailId(null)
                  setDetailData(null)
                }}
              >
                关闭
              </button>
            </div>
            <div className="max-h-[50vh] overflow-auto">
              <JsonDetailTables data={detailData} />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
