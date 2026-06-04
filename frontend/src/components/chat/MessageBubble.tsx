import type { ChatMessage } from '@/stores/useChatStore'
import {
  coalesceTextBlocksForDisplay,
  extractReasoningBlocks,
  segmentAssistantContent,
  stripReasoningForDisplay,
} from '@/lib/assistantContent'
import type { ContentBlock } from '@/types/message'
import { isHtmlLikeSegment } from '@/lib/htmlPreview'
import AssistantMarkdown from './AssistantMarkdown'
import ChatAvatar from './ChatAvatar'
import CopyTextButton from './CopyTextButton'
import FeedbackButtons from './FeedbackButtons'
import HtmlPreviewFrame from './HtmlPreviewFrame'
import ToolCallCard from './ToolCallCard'
import ThinkingBlock from './ThinkingBlock'

interface MessageBubbleProps {
  message: ChatMessage
  /** 助手显示名（头像兜底首字）。 */
  agentName: string
  agentAvatar?: string
  /** 当前是否正在为该助手消息流式生成（仅末条助手为 true）。 */
  isStreaming?: boolean
  feedbackContext?: {
    sessionId: string
    runId: string
    agentId: string
  }
  /** Render ```html blocks as iframe preview instead of monospace code. */
  htmlPreviewEnabled?: boolean
  /** When true, HTML segments are shown in the sticky deck bar — hide raw code here. */
  htmlInDeckPreview?: boolean
}

export default function MessageBubble({
  message,
  agentName,
  agentAvatar,
  isStreaming = false,
  feedbackContext,
  htmlPreviewEnabled = false,
  htmlInDeckPreview = false,
}: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const sid = message.serverMessageId
  const showFeedback =
    message.role === 'assistant' && !!sid && feedbackContext

  const reasoningBlocks = !isUser
    ? extractReasoningBlocks(message.content)
    : []
  const proseForMarkdown = !isUser
    ? stripReasoningForDisplay(message.content)
    : message.content
  const segments =
    !isUser && message.role === 'assistant'
      ? segmentAssistantContent(proseForMarkdown)
      : null
  const assistantEmptyStreaming =
    !isUser && isStreaming && !message.content.trim()

  // Streaming may attach text blocks; HTML preview uses full message.content.
  const blocks = message.blocks || []
  const structuredBlocks = blocks.filter(
    (b) => b.kind === 'tool_use' || b.kind === 'tool_result' || b.kind === 'thinking',
  )
  const hasStructuredBlocks = structuredBlocks.length > 0 && !isUser
  const displayStructuredBlocks = hasStructuredBlocks
    ? coalesceTextBlocksForDisplay(structuredBlocks)
    : []

  return (
    // 用户行：flex-row-reverse + justify-start → 视觉上 [气泡][头像] 整组靠右（勿用 justify-end，会变成靠左）
    <div
      className={`flex w-full min-w-0 justify-start gap-2.5 items-end ${
        isUser ? 'flex-row-reverse' : ''
      }`}
    >
      {!isUser && (
        <ChatAvatar variant="agent" label={agentName} imageUrl={agentAvatar} />
      )}
      {isUser && <ChatAvatar variant="user" label="我" />}
      <div
        className={`max-w-[min(85%,42rem)] rounded-2xl px-4 py-3 text-sm shadow-sm ${
          isUser
            ? 'bg-gradient-to-br from-primary-600 to-primary-700 text-white rounded-br-md'
            : 'bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 border border-slate-100 dark:border-slate-600 rounded-bl-md'
        }`}
      >
        {isUser ? (
          <>
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
            <div className="mt-2 flex justify-end">
              <CopyTextButton text={message.content} variant="user" />
            </div>
          </>
        ) : assistantEmptyStreaming ? (
          <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary-600" />
            </span>
            <span>正在生成回复…</span>
          </div>
        ) : (
          <div className="space-y-2">
            {/* Legacy reasoning blocks */}
            {reasoningBlocks.length > 0 && (
              <ThinkingBlock
                text={reasoningBlocks.map((b) => b.body).join('\n\n')}
                stepCount={reasoningBlocks.length}
              />
            )}

            {/* Tool / thinking blocks from streaming */}
            {hasStructuredBlocks && (
              <div className="space-y-2">
                {displayStructuredBlocks.map((b, i) => (
                  <BlockRenderer key={`${b.kind}-${i}`} block={b} />
                ))}
              </div>
            )}

            {/* Legacy toolCalls fallback */}
            {!hasStructuredBlocks && message.toolCalls && message.toolCalls.length > 0 && (
              <ToolCallCard toolCalls={message.toolCalls} />
            )}

            {/* Text + HTML segments always from message.content */}
            {segments?.map((seg, i) =>
              seg.kind === 'text' ? (
                <AssistantMarkdown key={i}>{seg.text}</AssistantMarkdown>
              ) : htmlInDeckPreview && isHtmlLikeSegment(seg.lang, seg.code) ? (
                <p
                  key={i}
                  className="text-[11px] text-slate-500 dark:text-slate-400 italic"
                >
                  HTML 段落已纳入上方幻灯片预览（共 {seg.code.length.toLocaleString()} 字符）
                </p>
              ) : htmlPreviewEnabled && isHtmlLikeSegment(seg.lang, seg.code) ? (
                <HtmlPreviewFrame key={i} html={seg.code} label="HTML 预览" />
              ) : (
                <pre
                  key={i}
                  className={`rounded-md px-3 py-2 text-xs overflow-x-auto font-mono leading-relaxed border ${
                    seg.lang === 'json'
                      ? 'bg-slate-900 text-slate-100 border-slate-700'
                      : 'bg-white/80 text-gray-900 border-gray-200 shadow-sm'
                  }`}
                >
                  {seg.code}
                </pre>
              ),
            )}
            {!segments && (
              <AssistantMarkdown>{proseForMarkdown}</AssistantMarkdown>
            )}
          </div>
        )}
        {!isUser && !assistantEmptyStreaming && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <CopyTextButton text={proseForMarkdown} variant="assistant" />
            {showFeedback && sid && feedbackContext && (
              <FeedbackButtons
                sessionId={feedbackContext.sessionId}
                runId={feedbackContext.runId}
                agentId={feedbackContext.agentId}
                messageId={sid}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function BlockRenderer({ block }: { block: ContentBlock }) {
  switch (block.kind) {
    case 'text':
      return <AssistantMarkdown>{block.text}</AssistantMarkdown>
    case 'thinking':
      return <ThinkingBlock text={block.text} />
    case 'tool_use':
      return (
        <ToolCallCard
          toolCalls={[
            {
              toolId: block.toolId,
              callId: block.callId,
              status: block.status,
              preview: block.preview,
            },
          ]}
        />
      )
    case 'tool_result':
      return (
        <div className="rounded-lg border border-slate-200/80 bg-slate-50 dark:bg-slate-900/50 px-3 py-2 text-[11px] text-slate-600 dark:text-slate-400">
          <span className="font-semibold">{block.toolId}</span> 结果：
          {block.content.length > 200
            ? `${block.content.slice(0, 197)}…`
            : block.content}
        </div>
      )
    default:
      return null
  }
}
