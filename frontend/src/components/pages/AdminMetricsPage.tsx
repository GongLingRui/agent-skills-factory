import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchProductMetricsSummary,
  type ProductMetricsSummary,
} from '@/api/adminBearer'

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10)
}

function fmtDate(s: string) {
  return s.replace(/-/g, '/')
}

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function fmtNum(v: number) {
  return v.toLocaleString('zh-CN')
}

export default function AdminMetricsPage() {
  const defaultRange = useMemo(() => {
    const end = new Date()
    const start = new Date()
    start.setDate(start.getDate() - 6)
    return { start: isoDate(start), end: isoDate(end) }
  }, [])
  const [start, setStart] = useState(defaultRange.start)
  const [end, setEnd] = useState(defaultRange.end)
  const [data, setData] = useState<ProductMetricsSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(async () => {
    setErr('')
    setLoading(true)
    try {
      const j = await fetchProductMetricsSummary(start, end)
      setData(j)
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : '加载失败')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [start, end])

  useEffect(() => {
    void load()
  }, [load])

  const summaryCards = data
    ? [
        {
          label: '月活用户（MAU）',
          hint: `近 ${data.mau_window_days} 天去重`,
          value: fmtNum(data.mau_rolling_distinct_users),
        },
        {
          label: '新建会话',
          hint: `${fmtDate(data.start_date)} – ${fmtDate(data.end_date)}`,
          value: fmtNum(data.new_chat_sessions),
        },
        {
          label: '新注册 Agent',
          hint: '统计期内上架数量',
          value: fmtNum(data.new_agents_registered),
        },
        {
          label: '用户满意度',
          hint: '点赞 / 全部反馈',
          value: fmtPct(data.feedback.satisfaction_rate),
        },
      ]
    : []

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-bold tracking-tight mb-1">产品指标</h1>
      <p className="text-sm text-slate-500 mb-6">
        汇总平台使用情况，帮助了解用户活跃度、会话增长与反馈质量。
      </p>
      {err && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {err}
        </div>
      )}
      <div className="flex flex-wrap gap-3 items-end mb-6">
        <label className="text-sm flex flex-col gap-1">
          <span className="text-slate-500">开始日期</span>
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="rounded-md border px-2 py-1.5"
          />
        </label>
        <label className="text-sm flex flex-col gap-1">
          <span className="text-slate-500">结束日期</span>
          <input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="rounded-md border px-2 py-1.5"
          />
        </label>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded-lg bg-primary-600 text-white text-sm px-4 py-2 font-medium disabled:opacity-50"
        >
          {loading ? '加载中…' : '刷新'}
        </button>
      </div>

      {loading && !data && (
        <p className="text-sm text-slate-500">正在加载指标…</p>
      )}

      {data && (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {summaryCards.map((c) => (
              <div
                key={c.label}
                className="rounded-xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)] p-4"
              >
                <div className="text-xs text-slate-500">{c.hint}</div>
                <div className="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">
                  {c.value}
                </div>
                <div className="mt-1 text-sm font-medium text-slate-700 dark:text-slate-300">
                  {c.label}
                </div>
              </div>
            ))}
          </div>

          <section>
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">
              每日活跃用户（DAU）
            </h2>
            <div className="overflow-x-auto rounded-xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)]">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-600 text-left text-xs text-slate-500">
                    <th className="px-4 py-2">日期</th>
                    <th className="px-4 py-2">活跃用户数</th>
                  </tr>
                </thead>
                <tbody>
                  {data.dau_by_day.length === 0 && (
                    <tr>
                      <td colSpan={2} className="px-4 py-6 text-center text-slate-500">
                        该时间段暂无活跃记录
                      </td>
                    </tr>
                  )}
                  {data.dau_by_day.map((row) => (
                    <tr
                      key={row.date}
                      className="border-b border-slate-100 dark:border-slate-700/80"
                    >
                      <td className="px-4 py-2">{fmtDate(row.date)}</td>
                      <td className="px-4 py-2">{fmtNum(row.distinct_users)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">
              用户反馈
            </h2>
            <div className="overflow-x-auto rounded-xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)]">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-600 text-left text-xs text-slate-500">
                    <th className="px-4 py-2">指标</th>
                    <th className="px-4 py-2">数值</th>
                    <th className="px-4 py-2">说明</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['点赞', fmtNum(data.feedback.thumbs_up), '用户认为回答有帮助'],
                    ['点踩', fmtNum(data.feedback.thumbs_down), '用户认为回答不满意'],
                    ['反馈总数', fmtNum(data.feedback.total), '点赞与点踩之和'],
                    [
                      '满意度',
                      fmtPct(data.feedback.satisfaction_rate),
                      '点赞占全部反馈的比例',
                    ],
                    [
                      '反馈参与率',
                      fmtPct(data.feedback.participation_vs_sessions),
                      '有反馈的会话占新建会话比例',
                    ],
                  ].map(([name, value, desc]) => (
                    <tr
                      key={name}
                      className="border-b border-slate-100 dark:border-slate-700/80"
                    >
                      <td className="px-4 py-2 font-medium">{name}</td>
                      <td className="px-4 py-2">{value}</td>
                      <td className="px-4 py-2 text-slate-500">{desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
