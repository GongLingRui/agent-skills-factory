import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getSkillCatalog,
  listSkillsCatalog,
  type SkillListRow,
  uploadSkillTarGz,
} from '@/api/adminCatalog'
import { JsonDetailTables } from '@/components/admin/JsonDetailTables'

export default function AdminSkillsPage() {
  const [rows, setRows] = useState<SkillListRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [detailId, setDetailId] = useState<string | null>(null)
  const [detailVer, setDetailVer] = useState<string | null>(null)
  const [detailData, setDetailData] = useState<unknown>(null)

  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadSkillId, setUploadSkillId] = useState('')
  const [uploadVersion, setUploadVersion] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const list = await listSkillsCatalog()
      setRows(list)
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

  const openDetail = async (id: string, version: string) => {
    setDetailId(id)
    setDetailVer(version)
    setDetailData('加载中…')
    try {
      const raw = await getSkillCatalog(id, version)
      setDetailData(raw)
    } catch (e: unknown) {
      setDetailData(e instanceof Error ? e.message : '加载失败')
    }
  }

  const submitUpload = async () => {
    if (!uploadFile || !uploadSkillId.trim() || !uploadVersion.trim()) {
      setError('请填写 Skill ID、版本并选择文件')
      return
    }
    setUploading(true)
    setError('')
    try {
      await uploadSkillTarGz(uploadFile, uploadSkillId.trim(), uploadVersion.trim())
      setUploadOpen(false)
      setUploadFile(null)
      setUploadSkillId('')
      setUploadVersion('')
      if (fileRef.current) fileRef.current.value = ''
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '上传失败')
    } finally {
      setUploading(false)
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
              <span>Skill 目录</span>
            </nav>
            <h1 className="text-xl font-bold">Skill 目录</h1>
            <p className="text-sm text-slate-500 mt-1">数据来自 GET /api/v1/skills；支持 tar.gz 上传入库</p>
          </div>
          <button
            type="button"
            onClick={() => setUploadOpen(true)}
            className="rounded-lg bg-primary-600 text-white text-sm px-4 py-2 font-medium"
          >
            上传 Skill
          </button>
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
                  <th className="px-4 py-3 font-semibold text-xs uppercase tracking-wide text-slate-500">risk</th>
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
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${r.risk_tier === 'high' ? 'bg-red-100 dark:bg-red-900/50 text-red-800 dark:text-red-200' : r.risk_tier === 'medium' ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-100' : 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-200'}`}>
                        {r.risk_tier ?? '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        className="text-primary-600 dark:text-primary-400 text-xs hover:underline"
                        onClick={() => void openDetail(r.id, r.version)}
                      >
                        查看详情
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
        )}
        {detailId && (
          <div className="rounded-xl border border-slate-200 dark:border-slate-700 p-4 space-y-2 bg-[var(--widget-surface)]">
            <div className="flex justify-between items-center gap-2">
              <p className="text-sm font-medium">
                详情{' '}
                <code className="text-xs">
                  {detailId}@{detailVer}
                </code>
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

        {uploadOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 space-y-4 shadow-xl">
              <h2 className="text-lg font-bold">上传 Skill（tar.gz）</h2>
              <label className="block text-sm space-y-1">
                <span className="text-slate-600 dark:text-slate-400">Skill ID</span>
                <input
                  value={uploadSkillId}
                  onChange={(e) => setUploadSkillId(e.target.value)}
                  className="w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-sm space-y-1">
                <span className="text-slate-600 dark:text-slate-400">版本</span>
                <input
                  value={uploadVersion}
                  onChange={(e) => setUploadVersion(e.target.value)}
                  className="w-full rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-sm space-y-1">
                <span className="text-slate-600 dark:text-slate-400">文件（.tar.gz）</span>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".tar.gz,application/gzip"
                  onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                  className="w-full text-sm"
                />
              </label>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setUploadOpen(false)}
                  className="rounded-lg border border-slate-200 dark:border-slate-600 text-sm px-4 py-2"
                >
                  取消
                </button>
                <button
                  type="button"
                  disabled={uploading}
                  onClick={() => void submitUpload()}
                  className="rounded-lg bg-primary-600 text-white text-sm px-4 py-2 font-medium disabled:opacity-50"
                >
                  {uploading ? '上传中…' : '上传'}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
