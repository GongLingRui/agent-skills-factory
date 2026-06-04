import { useCallback, useEffect, useState } from 'react'
import {
  fetchPlatformPolicies,
  postPlatformPolicy,
  putPlatformPolicy,
  fetchOrgPolicies,
  postOrgPolicy,
  putOrgPolicy,
} from '@/api/adminBearer'

interface PolicyRow {
  id: string
  version: number
  prompt: string
  enabled: boolean
  created_at: string | null
}

export default function AdminPoliciesPage() {
  const [platform, setPlatform] = useState<PolicyRow[]>([])
  const [orgDept, setOrgDept] = useState('')
  const [orgList, setOrgList] = useState<PolicyRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<'platform' | 'org'>('platform')

  const [form, setForm] = useState<{
    mode: 'create' | 'edit'
    id: string
    department: string
    prompt: string
    enabled: boolean
    originalId: string
  }>({ mode: 'create', id: '', department: '', prompt: '', enabled: true, originalId: '' })
  const [formOpen, setFormOpen] = useState(false)

  const loadPlatform = useCallback(async () => {
    setLoading(true)
    try {
      const d = await fetchPlatformPolicies()
      setPlatform(Array.isArray(d.policies) ? (d.policies as PolicyRow[]) : [])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadOrg = useCallback(async () => {
    if (!orgDept.trim()) {
      setOrgList([])
      return
    }
    setLoading(true)
    try {
      const d = await fetchOrgPolicies(orgDept.trim())
      setOrgList(Array.isArray(d.policies) ? (d.policies as PolicyRow[]) : [])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [orgDept])

  useEffect(() => {
    if (tab === 'platform') void loadPlatform()
    else void loadOrg()
  }, [tab, loadPlatform, loadOrg])

  const openCreate = () => {
    setForm({ mode: 'create', id: '', department: tab === 'org' ? orgDept : '', prompt: '', enabled: true, originalId: '' })
    setFormOpen(true)
  }

  const openEdit = (row: PolicyRow, dept?: string) => {
    setForm({
      mode: 'edit',
      id: row.id,
      department: dept || '',
      prompt: row.prompt,
      enabled: row.enabled,
      originalId: row.id,
    })
    setFormOpen(true)
  }

  const submit = async () => {
    setError('')
    try {
      if (tab === 'platform') {
        if (form.mode === 'create') {
          await postPlatformPolicy({ id: form.id.trim(), prompt: form.prompt.trim(), enabled: form.enabled })
        } else {
          await putPlatformPolicy(form.originalId, { id: form.id.trim(), prompt: form.prompt.trim(), enabled: form.enabled })
        }
        await loadPlatform()
      } else {
        if (!form.department.trim()) {
          setError('部门不能为空')
          return
        }
        if (form.mode === 'create') {
          await postOrgPolicy({ id: form.id.trim(), department: form.department.trim(), prompt: form.prompt.trim(), enabled: form.enabled })
        } else {
          await putOrgPolicy(form.originalId, { id: form.id.trim(), department: form.department.trim(), prompt: form.prompt.trim(), enabled: form.enabled })
        }
        await loadOrg()
      }
      setFormOpen(false)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '提交失败')
    }
  }

  const rows = tab === 'platform' ? platform : orgList

  return (
    <div className="min-h-[100dvh] bg-[var(--widget-bg)] text-slate-900 dark:text-slate-100">
      <header className="sticky top-0 z-10 border-b border-slate-200/80 dark:border-slate-700 bg-[var(--widget-surface)] px-4 py-4">
        <div className="mx-auto max-w-6xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold">策略管理</h1>
            <p className="text-sm text-slate-500 mt-1">平台策略与部门策略版本控制</p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setTab('platform')}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${tab === 'platform' ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900' : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600'}`}
            >
              平台策略
            </button>
            <button
              type="button"
              onClick={() => setTab('org')}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${tab === 'org' ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900' : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600'}`}
            >
              部门策略
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

        {tab === 'org' && (
          <div className="flex gap-2 items-center">
            <input
              value={orgDept}
              onChange={(e) => setOrgDept(e.target.value)}
              placeholder="输入部门代码"
              className="rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm w-48"
            />
            <button
              type="button"
              onClick={() => void loadOrg()}
              disabled={loading}
              className="rounded-lg bg-primary-600 text-white text-sm px-4 py-2 font-medium disabled:opacity-50"
            >
              查询
            </button>
          </div>
        )}

        <div className="flex justify-between items-center">
          <p className="text-sm text-slate-500">共 {rows.length} 条</p>
          <button
            type="button"
            onClick={openCreate}
            className="rounded-lg bg-primary-600 text-white text-sm px-4 py-2 font-medium"
          >
            新建策略
          </button>
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)]">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-600 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <th className="px-4 py-3 font-semibold">ID</th>
                <th className="px-4 py-3 font-semibold">版本</th>
                <th className="px-4 py-3 font-semibold">状态</th>
                <th className="px-4 py-3 font-semibold">Prompt 摘要</th>
                <th className="px-4 py-3 font-semibold text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.id}@${r.version}`} className="border-b border-slate-100 dark:border-slate-700/80">
                  <td className="px-4 py-3 font-mono text-xs">{r.id}</td>
                  <td className="px-4 py-3">{r.version}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${r.enabled ? 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-200' : 'bg-slate-200 dark:bg-slate-600 text-slate-700 dark:text-slate-200'}`}>
                      {r.enabled ? '启用' : '停用'}
                    </span>
                  </td>
                  <td className="px-4 py-3 max-w-xs truncate text-xs text-slate-600 dark:text-slate-400">{r.prompt}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => openEdit(r, tab === 'org' ? orgDept : undefined)}
                      className="text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700"
                    >
                      编辑
                    </button>
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

        {formOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-lg rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 space-y-4 shadow-xl">
              <h2 className="text-lg font-bold">{form.mode === 'create' ? '新建策略' : '编辑策略'}</h2>
              <label className="block text-sm space-y-1">
                <span className="text-slate-600 dark:text-slate-400">策略 ID</span>
                <input
                  value={form.id}
                  onChange={(e) => setForm((f) => ({ ...f, id: e.target.value }))}
                  className="w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                />
              </label>
              {tab === 'org' && (
                <label className="block text-sm space-y-1">
                  <span className="text-slate-600 dark:text-slate-400">部门</span>
                  <input
                    value={form.department}
                    onChange={(e) => setForm((f) => ({ ...f, department: e.target.value }))}
                    className="w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                  />
                </label>
              )}
              <label className="block text-sm space-y-1">
                <span className="text-slate-600 dark:text-slate-400">Prompt</span>
                <textarea
                  value={form.prompt}
                  onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
                  rows={6}
                  className="w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                />
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                />
                <span className="text-slate-600 dark:text-slate-400">启用（同 lineage 仅一条可启用）</span>
              </label>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setFormOpen(false)}
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
