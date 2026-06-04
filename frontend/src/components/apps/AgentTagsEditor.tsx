import { useCallback, useEffect, useRef, useState } from 'react'
import type { AgentItem } from '@/api/agents'
import { patchAgentTags } from '@/api/appStudio'
import { normalizeTag } from '@/lib/tagVocabulary'

interface AgentTagsEditorProps {
  agent: AgentItem
  canEdit: boolean
  onUpdated: (agentId: string, tags: string[]) => void
}

export default function AgentTagsEditor({
  agent,
  canEdit,
  onUpdated,
}: AgentTagsEditorProps) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<string[]>(agent.tags || [])
  const [input, setInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) {
      setDraft(agent.tags || [])
      setInput('')
      setErr('')
    }
  }, [open, agent.tags])

  useEffect(() => {
    if (open) {
      inputRef.current?.focus()
    }
  }, [open])

  const addDraftTag = useCallback(() => {
    const t = normalizeTag(input)
    if (!t) return
    setDraft((prev) => (prev.includes(t) ? prev : [...prev, t]))
    setInput('')
  }, [input])

  const save = async () => {
    setSaving(true)
    setErr('')
    try {
      const res = await patchAgentTags(agent.id, draft)
      onUpdated(agent.id, res.tags)
      setOpen(false)
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const tags = agent.tags || []

  return (
    <div
      className="mt-4"
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        {tags.length > 0 ? (
          tags.map((t) => (
            <span
              key={t}
              className="text-[11px] px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
            >
              {t}
            </span>
          ))
        ) : (
          <span className="text-[11px] text-slate-400">暂无标签</span>
        )}
        {canEdit && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="text-[11px] px-2 py-0.5 rounded-md border border-dashed border-slate-300 dark:border-slate-600 text-slate-500 hover:border-primary-400 hover:text-primary-600 transition-all opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto focus-visible:opacity-100 focus-visible:pointer-events-auto"
          >
            编辑标签
          </button>
        )}
      </div>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={() => !saving && setOpen(false)}
          role="presentation"
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-800 shadow-xl border border-slate-200 dark:border-slate-600 p-5"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-labelledby={`tags-editor-${agent.id}`}
          >
            <h3
              id={`tags-editor-${agent.id}`}
              className="font-semibold text-slate-900 dark:text-slate-100 truncate"
            >
              编辑标签 · {agent.name}
            </h3>
            <p className="text-xs text-slate-500 mt-1 font-mono truncate">
              {agent.id}
            </p>

            <div className="mt-4 flex flex-wrap gap-1.5 min-h-[2rem]">
              {draft.map((t) => (
                <span
                  key={t}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200"
                >
                  {t}
                  <button
                    type="button"
                    aria-label={`移除 ${t}`}
                    onClick={() =>
                      setDraft((prev) => prev.filter((x) => x !== t))
                    }
                    className="text-slate-400 hover:text-red-500 leading-none"
                  >
                    ×
                  </button>
                </span>
              ))}
              {draft.length === 0 && (
                <span className="text-xs text-slate-400">点击下方输入添加</span>
              )}
            </div>

            <div className="mt-3 flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addDraftTag()
                  }
                }}
                placeholder="新标签，回车添加"
                className="flex-1 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/30"
              />
              <button
                type="button"
                onClick={addDraftTag}
                className="rounded-lg px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700"
              >
                添加
              </button>
            </div>

            {err && (
              <p className="mt-2 text-xs text-red-600 dark:text-red-400">
                {err}
              </p>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                disabled={saving}
                onClick={() => setOpen(false)}
                className="rounded-lg px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => void save()}
                className="rounded-lg px-4 py-2 text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
              >
                {saving ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
