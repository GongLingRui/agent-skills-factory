import type { ChatMessage } from '@/stores/useChatStore'
import MessageBubble from './MessageBubble'

interface MessageListProps {
  messages: ChatMessage[]
  welcome: string
  agentTitle: string
  agentAvatar?: string
  quickActions?: Array<{ label: string; prompt: string }>
  /** 欢迎区快捷指令：将文案填入底栏输入框。 */
  onApplyQuickPrompt?: (prompt: string) => void
  sending: boolean
  feedbackContext?: {
    sessionId: string
    runId: string
    agentId: string
  }
  htmlPreviewEnabled?: boolean
  htmlInDeckPreview?: boolean
}

export default function MessageList({
  messages,
  welcome,
  agentTitle,
  agentAvatar,
  quickActions,
  onApplyQuickPrompt,
  sending,
  feedbackContext,
  htmlPreviewEnabled = false,
  htmlInDeckPreview = false,
}: MessageListProps) {
  return (
    <div className="flex-1 overflow-y-auto overflow-x-hidden px-3 sm:px-5 py-6 space-y-5 min-h-0 scroll-smooth">
      {messages.length === 0 && (
        <div className="max-w-xl mx-auto mt-4 sm:mt-10">
          <div className="relative overflow-hidden rounded-2xl border border-slate-200/80 dark:border-slate-600 bg-gradient-to-b from-white to-slate-50/90 dark:from-slate-800 dark:to-slate-900/90 p-6 sm:p-8 shadow-md shadow-slate-900/5 dark:shadow-black/20">
            <div
              className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full bg-primary-400/20 blur-3xl"
              aria-hidden
            />
            <p className="text-xs font-semibold uppercase tracking-wider text-primary-700 mb-2">
              {agentTitle}
            </p>
            <h2 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100 tracking-tight mb-3">
              开始对话
            </h2>
            <p className="text-slate-600 dark:text-slate-300 text-sm sm:text-base leading-relaxed whitespace-pre-wrap">
              {welcome}
            </p>
            {quickActions && quickActions.length > 0 && (
              <div className="mt-6">
                <p className="text-xs font-medium text-slate-500 mb-3">试试这些：</p>
                <div className="flex flex-wrap gap-2">
                  {quickActions.map((q) => (
                    <button
                      key={q.label}
                      type="button"
                      className="text-left text-xs sm:text-sm px-3 py-2 rounded-xl border border-slate-200 bg-white text-slate-800 hover:border-primary-300 hover:bg-primary-50/50 transition-colors shadow-sm"
                      onClick={() => onApplyQuickPrompt?.(q.prompt)}
                    >
                      {q.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      {messages.map((msg, index) => {
        const last = index === messages.length - 1
        const streamingThis =
          sending && last && msg.role === 'assistant'
        return (
          <MessageBubble
            key={msg.id}
            message={msg}
            agentName={agentTitle}
            agentAvatar={agentAvatar}
            isStreaming={streamingThis}
            feedbackContext={feedbackContext}
            htmlPreviewEnabled={htmlPreviewEnabled}
            htmlInDeckPreview={htmlInDeckPreview}
          />
        )
      })}
    </div>
  )
}
