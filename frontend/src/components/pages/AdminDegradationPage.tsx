import { useState } from 'react'
import { postDegradationLevel, postDegradationRecover } from '@/api/adminBearer'

export default function AdminDegradationPage() {
  const [level, setLevel] = useState(3)
  const [reason, setReason] = useState('ops: manual drill')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const run = async (fn: () => Promise<void>) => {
    setErr('')
    setMsg('')
    try {
      await fn()
      setMsg('已提交')
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : '请求失败')
    }
  }

  return (
    <div className="p-6 max-w-lg mx-auto">
      <h1 className="text-xl font-bold tracking-tight mb-1">降级控制</h1>
      <p className="text-sm text-slate-500 mb-6">
        <code className="text-xs">POST /api/v1/admin/degradation/level</code> ·{' '}
        <code className="text-xs">/recover</code>（prd §9.5、docs/33）。
      </p>
      {err && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {err}
        </div>
      )}
      {msg && (
        <div className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {msg}
        </div>
      )}
      <label className="block text-sm mb-2">
        <span className="text-slate-600">level（0–5）</span>
        <input
          type="number"
          min={0}
          max={5}
          value={level}
          onChange={(e) => setLevel(Number(e.target.value))}
          className="mt-1 w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-2 py-2"
        />
      </label>
      <label className="block text-sm mb-4">
        <span className="text-slate-600">reason</span>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void run(() => postDegradationLevel(level, reason))}
          className="rounded-lg bg-primary-600 text-white text-sm px-4 py-2 font-medium"
        >
          设置降级等级
        </button>
        <button
          type="button"
          onClick={() => void run(() => postDegradationRecover())}
          className="rounded-lg border border-slate-200 dark:border-slate-600 text-sm px-4 py-2"
        >
          恢复（level 0）
        </button>
      </div>
    </div>
  )
}
