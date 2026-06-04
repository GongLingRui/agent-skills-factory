import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getAgent, type AgentDetail } from '@/api/agents'

function readQuickActions(ui: Record<string, unknown> | undefined): Array<{
  label: string
  prompt: string
}> {
  const raw = ui?.quick_actions
  if (!Array.isArray(raw)) return []
  const out: Array<{ label: string; prompt: string }> = []
  for (const item of raw) {
    if (
      item &&
      typeof item === 'object' &&
      'label' in item &&
      'prompt' in item &&
      typeof (item as { label: unknown }).label === 'string' &&
      typeof (item as { prompt: unknown }).prompt === 'string'
    ) {
      out.push({
        label: (item as { label: string }).label,
        prompt: (item as { prompt: string }).prompt,
      })
    }
  }
  return out
}

/**
 * 独立「助手介绍」页：展示后端 ``description`` + ``ui_config`` 中与体验相关的文案（PRD §5 ui_config）。
 */
export default function AgentAboutPage() {
  const { agentId } = useParams<{ agentId: string }>()
  const navigate = useNavigate()
  const [agent, setAgent] = useState<AgentDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!agentId) return
    let cancelled = false
    void (async () => {
      try {
        const a = await getAgent(agentId)
        if (!cancelled) setAgent(a)
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : '加载失败')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [agentId])

  const ui = agent?.ui_config as Record<string, unknown> | undefined
  const title =
    (typeof ui?.title === 'string' ? ui.title : null) || agent?.name || 'Agent'
  const welcome =
    typeof ui?.welcome_message === 'string' ? ui.welcome_message : ''
  const quick = readQuickActions(ui)

  return (
    <div className="min-h-[100dvh] bg-[var(--widget-bg)] text-slate-900">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:py-12">
        <nav className="mb-8 flex flex-wrap items-center gap-4 text-sm">
          <button
            type="button"
            onClick={() => navigate(agentId ? `/apps/${agentId}` : '/')}
            className="inline-flex items-center gap-2 font-medium text-slate-600 hover:text-primary-700"
          >
            <span aria-hidden>←</span>
            返回对话
          </button>
          <Link
            to="/apps"
            className="font-medium text-primary-600 hover:text-primary-800"
          >
            应用库
          </Link>
        </nav>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-800 text-sm mb-6">
            {error}
          </div>
        )}

        {!agent && !error && (
          <div className="animate-pulse space-y-4">
            <div className="h-10 bg-slate-200 rounded-lg w-2/3" />
            <div className="h-4 bg-slate-100 rounded w-full" />
            <div className="h-4 bg-slate-100 rounded w-5/6" />
          </div>
        )}

        {agent && (
          <article className="rounded-2xl border border-slate-200/80 bg-[var(--widget-surface)] shadow-lg shadow-slate-900/5 overflow-hidden">
            <div className="bg-gradient-to-br from-primary-600 via-primary-600 to-primary-800 px-6 py-10 text-white">
              <p className="text-xs font-semibold uppercase tracking-widest text-white/70 mb-2">
                智能体说明
              </p>
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">{title}</h1>
              {agent.description && (
                <p className="mt-4 text-base text-white/95 leading-relaxed max-w-2xl">
                  {agent.description}
                </p>
              )}
            </div>
            <div className="px-6 py-8 space-y-8">
              {welcome && (
                <section>
                  <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
                    开场提示
                  </h2>
                  <div className="prose prose-slate prose-sm max-w-none whitespace-pre-wrap text-slate-700 leading-relaxed">
                    {welcome}
                  </div>
                </section>
              )}
              {quick.length > 0 && (
                <section>
                  <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
                    推荐怎么说（快捷指令）
                  </h2>
                  <p className="text-sm text-slate-600 mb-4">
                    在对话页底栏可一键填入以下内容，也可自行改写后再发送。
                  </p>
                  <ul className="space-y-3">
                    {quick.map((q) => (
                      <li
                        key={q.label}
                        className="rounded-xl border border-slate-100 bg-slate-50/80 px-4 py-3"
                      >
                        <div className="font-medium text-slate-900">{q.label}</div>
                        <div className="text-sm text-slate-600 mt-1 whitespace-pre-wrap">
                          {q.prompt}
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              <section className="rounded-xl bg-slate-50 border border-slate-100 px-4 py-4 text-sm text-slate-600 leading-relaxed">
                <strong className="text-slate-800">提示：</strong>
                本页文案来自应用配置（
                <code className="text-xs bg-white px-1 rounded border">ui_config</code>
                ），与后台执行策略分离；业务变更时可单独更新界面说明而不影响运行逻辑。
              </section>
            </div>
          </article>
        )}
      </div>
    </div>
  )
}
