import { useEffect, useState } from 'react'
import { postFeedback } from '@/api/agents'

type Props = {
  sessionId: string
  runId: string
  agentId: string
  messageId: string
}

export default function FeedbackButtons({
  sessionId,
  runId,
  agentId,
  messageId,
}: Props) {
  const [done, setDone] = useState<'up' | 'down' | null>(null)
  const [err, setErr] = useState('')
  /** docs/11-chat-widget：完整渲染约 1s 后再显示并淡入。 */
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const t = window.setTimeout(() => setReady(true), 1000)
    return () => clearTimeout(t)
  }, [])

  async function send(kind: 'thumbs_up' | 'thumbs_down') {
    if (done) return
    setErr('')
    try {
      await postFeedback({
        session_id: sessionId,
        message_id: messageId,
        run_id: runId,
        agent_id: agentId,
        feedback: kind,
      })
      setDone(kind === 'thumbs_up' ? 'up' : 'down')
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : '反馈失败')
    }
  }

  return (
    <div
      className={`flex items-center gap-2 transition-opacity duration-300 ${
        ready ? 'opacity-100' : 'opacity-0 pointer-events-none select-none'
      }`}
      aria-hidden={!ready}
    >
      <button
        type="button"
        disabled={!!done}
        className="text-xs px-2 py-0.5 rounded border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50 dark:text-slate-200"
        onClick={() => void send('thumbs_up')}
        aria-label="有帮助"
      >
        👍
      </button>
      <button
        type="button"
        disabled={!!done}
        className="text-xs px-2 py-0.5 rounded border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50 dark:text-slate-200"
        onClick={() => void send('thumbs_down')}
        aria-label="需改进"
      >
        👎
      </button>
      {done && <span className="text-xs text-gray-400">已记录</span>}
      {err && <span className="text-xs text-red-600">{err}</span>}
    </div>
  )
}
