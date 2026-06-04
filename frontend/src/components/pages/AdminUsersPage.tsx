import { useCallback, useEffect, useState } from 'react'
import { fetchAdminDepartments, fetchAdminUsers, putUserRoles } from '@/api/adminBearer'

interface UserRow {
  user_id: string
  name: string
  department: string
  roles: string[]
  created_at?: string | null
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserRow[]>([])
  const [depts, setDepts] = useState<Array<{ code: string; name: string; parent?: string | null }>>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [filterDept, setFilterDept] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [editUser, setEditUser] = useState<UserRow | null>(null)
  const [rolesInput, setRolesInput] = useState('')
  const [reasonInput, setReasonInput] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [u, d] = await Promise.all([
        fetchAdminUsers(page),
        fetchAdminDepartments(),
      ])
      setUsers(u.items)
      setTotal(u.total)
      setDepts(Array.isArray(d.departments) ? (d.departments as Array<{ code: string; name: string; parent?: string | null }>) : [])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败')
      setUsers([])
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    void load()
  }, [load])

  const openEdit = (user: UserRow) => {
    setEditUser(user)
    setRolesInput(user.roles.join(', '))
    setReasonInput('')
  }

  const submitRoles = async () => {
    if (!editUser) return
    const roles = rolesInput
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean)
    setError('')
    try {
      await putUserRoles(editUser.user_id, { roles, reason: reasonInput || undefined })
      setEditUser(null)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '保存失败')
    }
  }

  const filteredUsers = filterDept
    ? users.filter((u) => u.department === filterDept)
    : users

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="min-h-[100dvh] bg-[var(--widget-bg)] text-slate-900 dark:text-slate-100">
      <header className="sticky top-0 z-10 border-b border-slate-200/80 dark:border-slate-700 bg-[var(--widget-surface)] px-4 py-4">
        <div className="mx-auto max-w-6xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold">用户与部门</h1>
            <p className="text-sm text-slate-500 mt-1">门户 IAM 快照 + 本系统角色 overlay</p>
          </div>
          <div className="flex gap-2 items-center">
            <select
              value={filterDept}
              onChange={(e) => setFilterDept(e.target.value)}
              className="rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-2 py-1.5 text-sm"
            >
              <option value="">全部部门</option>
              {depts.map((d) => (
                <option key={d.code} value={d.code}>
                  {d.name || d.code}
                </option>
              ))}
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

        <div className="flex items-center justify-between text-xs text-slate-500">
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
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-600 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <th className="px-4 py-3 font-semibold">User ID</th>
                <th className="px-4 py-3 font-semibold">姓名</th>
                <th className="px-4 py-3 font-semibold">部门</th>
                <th className="px-4 py-3 font-semibold">角色</th>
                <th className="px-4 py-3 font-semibold text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((r) => (
                <tr key={r.user_id} className="border-b border-slate-100 dark:border-slate-700/80">
                  <td className="px-4 py-3 font-mono text-xs">{r.user_id}</td>
                  <td className="px-4 py-3">{r.name || '—'}</td>
                  <td className="px-4 py-3 text-xs">{r.department || '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {r.roles.map((role) => (
                        <span key={role} className="inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
                          {role}
                        </span>
                      ))}
                      {r.roles.length === 0 && <span className="text-xs text-slate-400">—</span>}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => openEdit(r)}
                      className="text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700"
                    >
                      修改角色
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && filteredUsers.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-500">暂无数据</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="rounded-xl border border-slate-200/80 dark:border-slate-600 bg-[var(--widget-surface)] p-4">
          <h2 className="text-sm font-semibold mb-2">部门树</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-600 text-left text-slate-500">
                  <th className="px-3 py-2 font-medium">Code</th>
                  <th className="px-3 py-2 font-medium">Name</th>
                  <th className="px-3 py-2 font-medium">Parent</th>
                </tr>
              </thead>
              <tbody>
                {depts.map((d) => (
                  <tr key={d.code} className="border-b border-slate-100 dark:border-slate-700/80">
                    <td className="px-3 py-2 font-mono">{d.code}</td>
                    <td className="px-3 py-2">{d.name || '—'}</td>
                    <td className="px-3 py-2 font-mono">{d.parent || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {editUser && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 space-y-4 shadow-xl">
              <h2 className="text-lg font-bold">修改角色</h2>
              <div className="text-sm text-slate-500">
                <p className="font-medium text-slate-700 dark:text-slate-300">{editUser.name || editUser.user_id}</p>
                <p className="font-mono text-xs mt-1">{editUser.user_id}</p>
              </div>
              <label className="block text-sm space-y-1">
                <span className="text-slate-600 dark:text-slate-400">角色（逗号分隔）</span>
                <input
                  value={rolesInput}
                  onChange={(e) => setRolesInput(e.target.value)}
                  placeholder="platform_admin, agent.admin ..."
                  className="w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-sm space-y-1">
                <span className="text-slate-600 dark:text-slate-400">变更原因（可选）</span>
                <input
                  value={reasonInput}
                  onChange={(e) => setReasonInput(e.target.value)}
                  className="w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                />
              </label>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditUser(null)}
                  className="rounded-lg border border-slate-200 dark:border-slate-600 text-sm px-4 py-2"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void submitRoles()}
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
