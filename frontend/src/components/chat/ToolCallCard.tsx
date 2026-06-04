import type { AssistantToolCallRow } from '@/stores/useChatStore'

interface ToolCallCardProps {
  toolCalls: AssistantToolCallRow[]
}

function toolLabel(toolId: string): string {
  const map: Record<string, string> = {
    'doc.extract': '文档提取',
    'kb.search': '知识检索',
    'read_reference': '参考阅读',
    'risk.rule_check': '规则检查',
  }
  return map[toolId] || toolId
}

function toolMonogram(toolId: string): string {
  const t = toolId.replace(/[^a-z]/gi, '')
  return (t.slice(0, 2) || '?').toUpperCase()
}

function toolAccentClass(toolId: string): string {
  if (toolId === 'doc.extract') {
    return 'from-amber-500 to-orange-600'
  }
  if (toolId === 'kb.search') {
    return 'from-sky-500 to-cyan-600'
  }
  if (toolId === 'read_reference') {
    return 'from-violet-500 to-purple-600'
  }
  return 'from-slate-500 to-slate-700'
}

function formatToolSummary(row: AssistantToolCallRow): string | null {
  if (row.status === 'running') {
    return null
  }
  if (!row.preview) {
    return row.status === 'error' ? '失败' : '完成'
  }
  if (row.status === 'error') {
    try {
      const j = JSON.parse(row.preview) as { code?: string; message?: string }
      if (j?.message && j?.code) {
        return `${j.message}（${j.code}）`
      }
      if (j?.message) return String(j.message)
      if (j?.code) return String(j.code)
    } catch {
      /* fall through */
    }
    return row.preview.length > 200 ? `${row.preview.slice(0, 197)}…` : row.preview
  }
  return row.preview.length > 220
    ? `${row.preview.slice(0, 217)}…`
    : row.preview
}

function formatSuccessToolBody(row: AssistantToolCallRow): string | null {
  if (row.status !== 'done' || !row.preview) return null
  try {
    const j = JSON.parse(row.preview) as Record<string, unknown>
    if (typeof j.text === 'string') {
      const t = j.text.trim()
      if (!t) return null
      return t.length > 200 ? `${t.slice(0, 197)}…` : t
    }
  } catch {
    /* ignore */
  }
  return null
}

export default function ToolCallCard({ toolCalls }: ToolCallCardProps) {
  if (!toolCalls || toolCalls.length === 0) return null
  return (
    <div className="rounded-xl border border-slate-200/90 bg-gradient-to-b from-slate-50 to-white dark:from-slate-900/80 dark:to-slate-950/90 dark:border-slate-600/90 shadow-sm overflow-hidden">
      <div className="px-3 py-2 border-b border-slate-200/80 dark:border-slate-700/80 bg-slate-100/60 dark:bg-slate-800/50">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300">
          工具调用
        </span>
      </div>
      <ul className="divide-y divide-slate-100 dark:divide-slate-700/80">
        {toolCalls.map((tc, idx) => {
          const summary = formatToolSummary(tc)
          const successBody = formatSuccessToolBody(tc)
          return (
            <li
              key={`${tc.toolId}-${idx}-${tc.callId || ''}`}
              className="flex gap-3 px-3 py-3"
            >
              <div
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-[11px] font-bold tracking-tight text-white shadow-md ${toolAccentClass(tc.toolId)}`}
                aria-hidden
              >
                {toolMonogram(tc.toolId)}
              </div>
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-slate-900 dark:text-slate-50">
                    {toolLabel(tc.toolId)}
                  </span>
                  {tc.status === 'running' && (
                    <span className="text-[11px] text-slate-500 dark:text-slate-400">
                      已提交，执行中…
                    </span>
                  )}
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                      tc.status === 'error'
                        ? 'bg-red-100 text-red-800 dark:bg-red-950/80 dark:text-red-200'
                        : tc.status === 'running'
                          ? 'bg-amber-100 text-amber-900 dark:bg-amber-950/60 dark:text-amber-100'
                          : 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-100'
                    }`}
                  >
                    {tc.status === 'running'
                      ? '执行中'
                      : tc.status === 'error'
                        ? '失败'
                        : '完成'}
                  </span>
                </div>
                {summary && (
                  <p className="text-[11px] leading-snug text-slate-600 dark:text-slate-400 m-0">
                    {summary}
                  </p>
                )}
                {successBody && (
                  <pre className="mt-1 max-h-36 overflow-y-auto rounded-lg border border-slate-200/80 bg-slate-900/[0.04] dark:border-slate-600/60 dark:bg-black/30 px-2.5 py-2 text-[11px] leading-relaxed text-slate-800 dark:text-slate-200 whitespace-pre-wrap break-words font-sans m-0">
                    {successBody}
                  </pre>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
