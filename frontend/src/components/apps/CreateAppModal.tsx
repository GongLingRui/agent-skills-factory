import { useEffect, useMemo, useState } from 'react'
import {
  composeAgentFromRequirements,
  fetchStudioToolCatalog,
  type ToolCatalogGroupTool,
  type ToolCatalogPreset,
  type ToolCatalogResponse,
} from '@/api/appStudio'

interface CreateAppModalProps {
  open: boolean
  onClose: () => void
  onCreated: (agentId: string) => void
}

function buildToolIndex(
  groups: ToolCatalogResponse['groups'],
): Map<string, ToolCatalogGroupTool> {
  const m = new Map<string, ToolCatalogGroupTool>()
  for (const g of groups) {
    for (const t of g.tools) {
      m.set(t.id, t)
    }
  }
  return m
}

function StudioToolList({
  title,
  hint,
  toolIds,
  toolIndex,
}: {
  title: string
  hint?: string
  toolIds: string[]
  toolIndex: Map<string, ToolCatalogGroupTool>
}) {
  if (toolIds.length === 0) {
    return (
      <p className="text-xs text-slate-400 py-2">暂无工具项</p>
    )
  }

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-600 bg-slate-50/80 dark:bg-slate-950/40 overflow-hidden">
      <div className="px-3 py-2 border-b border-slate-200/80 dark:border-slate-700 bg-white/60 dark:bg-slate-900/60">
        <p className="text-xs font-medium text-slate-700 dark:text-slate-200">
          {title}
          <span className="ml-1.5 font-normal text-slate-400">
            ({toolIds.length} 项)
          </span>
        </p>
        {hint && (
          <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 leading-snug">
            {hint}
          </p>
        )}
      </div>
      <ul className="max-h-52 overflow-y-auto divide-y divide-slate-200/70 dark:divide-slate-700/80">
        {toolIds.map((id) => {
          const meta = toolIndex.get(id)
          const available = meta?.available ?? false
          return (
            <li
              key={id}
              className="px-3 py-2 flex flex-col gap-0.5 hover:bg-white/70 dark:hover:bg-slate-900/50"
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span className="text-xs font-medium text-slate-800 dark:text-slate-100">
                  {meta?.name || id}
                </span>
                <span className="text-[10px] font-mono text-slate-400">
                  {id}
                </span>
                {!available && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300">
                    未启用
                  </span>
                )}
              </div>
              {meta?.description && (
                <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-snug">
                  {meta.description}
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default function CreateAppModal({
  open,
  onClose,
  onCreated,
}: CreateAppModalProps) {
  const [requirements, setRequirements] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [catalog, setCatalog] = useState<ToolCatalogResponse | null>(null)
  const [toolPreset, setToolPreset] = useState<string>('')

  useEffect(() => {
    if (!open) return
    void fetchStudioToolCatalog()
      .then(setCatalog)
      .catch(() => setCatalog(null))
  }, [open])

  const presets = catalog?.presets ?? []
  const toolIndex = useMemo(
    () => buildToolIndex(catalog?.groups ?? []),
    [catalog],
  )

  const activePreset = useMemo(
    () => presets.find((p) => p.id === toolPreset),
    [presets, toolPreset],
  )

  const displayedToolIds = useMemo(() => {
    if (activePreset) return activePreset.tools_expanded
    return catalog?.default_tools_expanded ?? []
  }, [activePreset, catalog])

  if (!open) return null

  const submit = async () => {
    const text = requirements.trim()
    if (text.length < 4) {
      setError('请至少用几句话描述你想创建的应用')
      return
    }
    setBusy(true)
    setError('')
    try {
      const res = await composeAgentFromRequirements(text, {
        toolPreset: toolPreset || undefined,
      })
      setRequirements('')
      setToolPreset('')
      onCreated(res.id)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '创建失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 px-4">
      <div
        className="w-full max-w-2xl max-h-[90vh] flex flex-col rounded-2xl border border-slate-200/90 dark:border-slate-600 bg-[var(--widget-surface)] dark:bg-slate-900 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-app-title"
      >
        <div className="px-5 pt-5 pb-3 border-b border-slate-200/80 dark:border-slate-700 shrink-0">
          <h2
            id="create-app-title"
            className="text-lg font-bold text-slate-900 dark:text-slate-100"
          >
            快速创建应用
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
            描述业务场景；若无合适 Skill 将自动创建。可选工具包（参考 OpenClaw
            profiles）。
          </p>
        </div>
        <div className="p-5 space-y-4 overflow-y-auto flex-1">
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-2">
              工具包（可选）
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => setToolPreset('')}
                className={`text-xs px-2.5 py-1 rounded-full border ${
                  !toolPreset
                    ? 'bg-primary-600 text-white border-primary-600'
                    : 'border-slate-200 dark:border-slate-600'
                }`}
              >
                自动推断
              </button>
              {presets.map((p: ToolCatalogPreset) => (
                <button
                  key={p.id}
                  type="button"
                  disabled={busy}
                  title={p.description}
                  onClick={() => setToolPreset(p.id)}
                  className={`text-xs px-2.5 py-1 rounded-full border ${
                    toolPreset === p.id
                      ? 'bg-primary-600 text-white border-primary-600'
                      : 'border-slate-200 dark:border-slate-600'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {activePreset?.description && (
              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-2">
                {activePreset.description}
              </p>
            )}
          </div>

          <StudioToolList
            title={
              activePreset
                ? `「${activePreset.label}」包含的工具`
                : '自动推断时的参考默认工具'
            }
            hint={
              activePreset
                ? undefined
                : '实际创建时会结合需求描述智能选配，以下为未指定工具包时的基础默认集'
            }
            toolIds={displayedToolIds}
            toolIndex={toolIndex}
          />

          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-2">
              应用需求
            </label>
            <textarea
              value={requirements}
              onChange={(e) => setRequirements(e.target.value)}
              rows={5}
              disabled={busy}
              placeholder="例如：我需要一个帮助分析部门推诿、指标博弈等组织问题的顾问，能输出根因诊断和干预建议…"
              className="w-full rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-950 px-3 py-2.5 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary-500/40 resize-y min-h-[100px]"
            />
          </div>
          {error && (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          )}
        </div>
        <div className="px-5 pb-5 flex justify-end gap-2 shrink-0">
          <button
            type="button"
            disabled={busy}
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium border border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void submit()}
            className="rounded-lg px-4 py-2 text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 min-w-[7rem]"
          >
            {busy ? '创建中…' : '创建并打开'}
          </button>
        </div>
      </div>
    </div>
  )
}
