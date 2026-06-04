import { useMemo, useState } from 'react'
import type { AgentItem } from '@/api/agents'
import { patchAgentTags } from '@/api/appStudio'
import { normalizeTag, saveExtraTags } from '@/lib/tagVocabulary'

interface TagFilterBarProps {
  tags: string[]
  tagFilter: string
  onTagFilterChange: (tag: string) => void
  canManage: boolean
  agents: AgentItem[]
  extraTags: string[]
  onExtraTagsChange: (tags: string[]) => void
  onAgentsTagsChange: (updates: Array<{ id: string; tags: string[] }>) => void
}

export default function TagFilterBar({
  tags,
  tagFilter,
  onTagFilterChange,
  canManage,
  agents,
  extraTags,
  onExtraTagsChange,
  onAgentsTagsChange,
}: TagFilterBarProps) {
  const [expanded, setExpanded] = useState(false)
  const [manageOpen, setManageOpen] = useState(false)
  const [newTag, setNewTag] = useState('')
  const [editingTag, setEditingTag] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [manageErr, setManageErr] = useState('')

  const tagCounts = useMemo(() => {
    const m = new Map<string, number>()
    for (const a of agents) {
      for (const t of a.tags || []) {
        const n = normalizeTag(t)
        if (n) m.set(n, (m.get(n) || 0) + 1)
      }
    }
    return m
  }, [agents])

  const persistExtra = (next: string[]) => {
    onExtraTagsChange(next)
    saveExtraTags(next)
  }

  const addVocabularyTag = () => {
    const t = normalizeTag(newTag)
    if (!t || tags.includes(t)) {
      setNewTag('')
      return
    }
    persistExtra([...extraTags, t])
    setNewTag('')
  }

  const applyBulkTagUpdate = async (
    mutator: (current: string[]) => string[],
  ) => {
    const updates: Array<{ id: string; tags: string[] }> = []
    for (const a of agents) {
      const current = a.tags || []
      const next = mutator(current)
      if (next.join('\0') !== current.join('\0')) {
        updates.push({ id: a.id, tags: next })
      }
    }
    if (updates.length === 0) return
    setBusy(true)
    setManageErr('')
    try {
      await Promise.all(
        updates.map((u) => patchAgentTags(u.id, u.tags)),
      )
      onAgentsTagsChange(updates)
    } catch (e: unknown) {
      setManageErr(e instanceof Error ? e.message : '批量更新失败')
      throw e
    } finally {
      setBusy(false)
    }
  }

  const renameTag = async (oldTag: string) => {
    const nextTag = normalizeTag(editValue)
    if (!nextTag || nextTag === oldTag) {
      setEditingTag(null)
      return
    }
    if (tags.includes(nextTag)) {
      setManageErr(`标签「${nextTag}」已存在`)
      return
    }
    try {
      await applyBulkTagUpdate((current) =>
        current.map((t) => (t === oldTag ? nextTag : t)),
      )
      persistExtra(extraTags.map((t) => (t === oldTag ? nextTag : t)))
      if (tagFilter === oldTag) onTagFilterChange(nextTag)
      setEditingTag(null)
      setEditValue('')
    } catch {
      /* err shown via manageErr */
    }
  }

  const deleteTag = async (tag: string) => {
    if (!window.confirm(`删除标签「${tag}」？将从所有应用中移除。`)) return
    try {
      await applyBulkTagUpdate((current) => current.filter((t) => t !== tag))
      persistExtra(extraTags.filter((t) => t !== tag))
      if (tagFilter === tag) onTagFilterChange('all')
    } catch {
      /* err shown via manageErr */
    }
  }

  const chipClass = (active: boolean) =>
    `rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
      active
        ? 'bg-primary-600 text-white'
        : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700'
    }`

  return (
    <>
      <div className="mx-auto max-w-6xl px-4 pb-3">
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300 hover:text-primary-700 dark:hover:text-primary-400"
            aria-expanded={expanded}
          >
            <svg
              className={`w-4 h-4 transition-transform ${expanded ? 'rotate-180' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
            标签筛选
            {tags.length > 0 && (
              <span className="text-slate-400">({tags.length})</span>
            )}
          </button>

          {!expanded && tagFilter !== 'all' && (
            <span className={chipClass(true)}>{tagFilter}</span>
          )}

          {canManage && (
            <button
              type="button"
              onClick={() => {
                setManageOpen(true)
                setManageErr('')
              }}
              className="text-xs px-2.5 py-1 rounded-full border border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:border-primary-400 hover:text-primary-600"
            >
              管理标签
            </button>
          )}
        </div>

        {expanded && (
          <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto pr-1">
            <button
              type="button"
              onClick={() => onTagFilterChange('all')}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                tagFilter === 'all'
                  ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900'
                  : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700'
              }`}
            >
              全部
            </button>
            {tags.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => onTagFilterChange(t)}
                className={chipClass(tagFilter === t)}
              >
                {t}
              </button>
            ))}
          </div>
        )}
      </div>

      {manageOpen && canManage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={() => !busy && setManageOpen(false)}
          role="presentation"
        >
          <div
            className="w-full max-w-lg max-h-[85vh] flex flex-col rounded-2xl bg-white dark:bg-slate-800 shadow-xl border border-slate-200 dark:border-slate-600"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-labelledby="tag-manage-title"
          >
            <div className="p-5 border-b border-slate-200 dark:border-slate-700 shrink-0">
              <h3
                id="tag-manage-title"
                className="font-semibold text-slate-900 dark:text-slate-100"
              >
                管理标签
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                重命名或删除会同步更新所有使用该标签的应用
              </p>
              <div className="mt-3 flex gap-2">
                <input
                  type="text"
                  value={newTag}
                  onChange={(e) => setNewTag(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addVocabularyTag()
                    }
                  }}
                  placeholder="添加新标签到筛选列表"
                  className="flex-1 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/30"
                />
                <button
                  type="button"
                  disabled={busy}
                  onClick={addVocabularyTag}
                  className="rounded-lg px-3 py-2 text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
                >
                  添加
                </button>
              </div>
            </div>

            <ul className="overflow-y-auto flex-1 p-3 space-y-1">
              {tags.map((t) => (
                <li
                  key={t}
                  className="flex items-center gap-2 rounded-lg px-2 py-2 hover:bg-slate-50 dark:hover:bg-slate-700/50"
                >
                  {editingTag === t ? (
                    <>
                      <input
                        type="text"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void renameTag(t)
                          if (e.key === 'Escape') setEditingTag(null)
                        }}
                        className="flex-1 rounded-md border border-slate-200 dark:border-slate-600 px-2 py-1 text-sm bg-white dark:bg-slate-900"
                        autoFocus
                      />
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void renameTag(t)}
                        className="text-xs text-primary-600 hover:underline disabled:opacity-50"
                      >
                        保存
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingTag(null)}
                        className="text-xs text-slate-500 hover:underline"
                      >
                        取消
                      </button>
                    </>
                  ) : (
                    <>
                      <span className="flex-1 text-sm text-slate-800 dark:text-slate-200">
                        {t}
                        <span className="ml-2 text-xs text-slate-400">
                          {tagCounts.get(t) ?? 0} 个应用
                        </span>
                      </span>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          setEditingTag(t)
                          setEditValue(t)
                          setManageErr('')
                        }}
                        className="text-xs text-slate-500 hover:text-primary-600 disabled:opacity-50"
                      >
                        重命名
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void deleteTag(t)}
                        className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
                      >
                        删除
                      </button>
                    </>
                  )}
                </li>
              ))}
              {tags.length === 0 && (
                <li className="text-sm text-slate-400 text-center py-8">
                  暂无标签，可先在上方添加
                </li>
              )}
            </ul>

            {manageErr && (
              <p className="px-5 pb-2 text-xs text-red-600 dark:text-red-400 shrink-0">
                {manageErr}
              </p>
            )}

            <div className="p-4 border-t border-slate-200 dark:border-slate-700 flex justify-end shrink-0">
              <button
                type="button"
                disabled={busy}
                onClick={() => setManageOpen(false)}
                className="rounded-lg px-4 py-2 text-sm font-medium bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 disabled:opacity-50"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
