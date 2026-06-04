import { useCallback, useEffect, useState } from 'react'
import { fetchTokenQuotas, putTokenQuota } from '@/api/adminBearer'

interface QuotaRow {
  scope: string
  scope_id: string
  budget_tokens: number
  used_tokens: number
  usage_rate: number
  period: string
  period_start: string
  period_end: string
}

export default function AdminQuotasPage() {
  const [rows, setRows] = useState<QuotaRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [filterScope, setFilterScope] = useState('')

  const [editRow, setEditRow] = useState<QuotaRow | null>(null)
  const [budgetInput, setBudgetInput] = useState('')
  const [nextPeriod, setNextPeriod] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const d = await fetchTokenQuotas()
      setRows(Array.isArray(d.items) ? (d.items as QuotaRow[]) : [])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const openEdit = (row: QuotaRow) => {
    setEditRow(row)
    setBudgetInput(String(row.budget_tokens))
    setNextPeriod(false)
  }

  const submit = async () => {
    if (!editRow) return
    const budget = Number(budgetInput)
    if (!Number.isFinite(budget) || budget < 0) {
      setError('预算必须为非负数')
      return
    }
    setError('')
    try {
      await putTokenQuota(editRow.scope, editRow.scope_id, {
        budget_tokens: budget,
        effective_next_period: nextPeriod,
      })
      setEditRow(null)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '保存失败')
    }
  }

  const filtered = filterScope
    ? rows.filter((r) => r.scope === filterScope)
    : rows

  return (
    <div className="min-h-[100dvh] bg-[var(--widget-bg)] text-slate-900 dark:text-slate-100">
      <header className="sticky top-0 z-10 border-b border-slate-200/80 dark:border-slate-700 bg-[var(--widget-surface)] px-4 py-4">
        <div className="mx-auto max-w-6xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold">Token 预算</h1>
            <p className="text-sm text-slate-500 mt-1">平台 / 部门 / Agent / 用户级额度管理</p>
          </div>
          <div className="flex gap-2">
            <select
              value={filterScope}
              onChange={(e) => setFilterScope(e.target.value)}
              className="rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-2 py-1.5 text-sm"
            >
              <option value="">全部 scope</option>
              <option value="platform">platform</option>
              <option value="department">department</option>
              <option value="agent">agent</option>
              <option value="user">user</option>
            </select>
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="rounded-lg bg-primary-600 text-white text-sm px-4 py-2 font-medium disabled:opacity-50"
            >
              刷新
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 space-y-4">
        {error && (
          <div className="mb-4 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-200">
            {error}
          </div>
        )}

        <div className="overflow-x-auto rounded-xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)]">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-600 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <th className="px-4 py-3 font-semibold">Scope</th>
                <th className="px-4 py-3 font-semibold">Scope ID</th>
                <th className="px-4 py-3 font-semibold">周期</th>
                <th className="px-4 py-3 font-semibold">预算</th>
                <th className="px-4 py-3 font-semibold">已用</th>
                <th className="px-4 py-3 font-semibold">使用率</th>
                <th className="px-4 py-3 font-semibold text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={`${r.scope}:${r.scope_id}:${r.period}`} className="border-b border-slate-100 dark:border-slate-700/80">
                  <td className="px-4 py-3 text-xs font-medium">{r.scope}</td>
                  <td className="px-4 py-3 font-mono text-xs">{r.scope_id}</td>
                  <td className="px-4 py-3 text-xs">{r.period}</td>
                  <td className="px-4 py-3">{r.budget_tokens.toLocaleString()}</td>
                  <td className="px-4 py-3">{r.used_tokens.toLocaleString()}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-2 rounded bg-slate-200 dark:bg-slate-700 overflow-hidden">
                        <div
                          className={`h-full rounded ${r.usage_rate >= 0.9 ? 'bg-red-500' : r.usage_rate >= 0.7 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                          style={{ width: `${Math.min(100, r.usage_rate * 100)}%` }}
                        />
                      </div>
                      <span className="text-xs">{(r.usage_rate * 100).toFixed(1)}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => openEdit(r)}
                      className="text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700"
                    >
                      调整预算
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">暂无数据</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {editRow && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 space-y-4 shadow-xl">
              <h2 className="text-lg font-bold">调整预算</h2>
              <div className="text-sm text-slate-500 space-y-1">
                <p>
                  <span className="font-medium text-slate-700 dark:text-slate-300">Scope:</span> {editRow.scope} / {editRow.scope_id}
                </p>
                <p>
                  <span className="font-medium text-slate-700 dark:text-slate-300">周期:</span> {editRow.period}
                </p>
              </div>
              <label className="block text-sm space-y-1">
                <span className="text-slate-600 dark:text-slate-400">新预算（tokens）</span>
                <input
                  type="number"
                  min={0}
                  value={budgetInput}
                  onChange={(e) => setBudgetInput(e.target.value)}
                  className="w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                />
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={nextPeriod}
                  onChange={(e) => setNextPeriod(e.target.checked)}
                />
                <span className="text-slate-600 dark:text-slate-400">下月生效</span>
              </label>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditRow(null)}
                  className="rounded-lg border border-slate-200 dark:border-slate-600 text-sm px-4 py-2"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void submit()}
                  className="rounded-lg bg-primary-600 text-white text-sm px-4 py-2 font-medium"
                >
                  保存
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
