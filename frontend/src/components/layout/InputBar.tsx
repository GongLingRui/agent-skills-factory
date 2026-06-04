import { useRef, useState } from 'react'
import type { AttachmentPolicy } from '@/lib/attachmentPolicy'
import {
  attachmentInputAccept,
  isAttachmentUploadAllowed,
  validateLocalAttachment,
} from '@/lib/attachmentPolicy'

interface QuickAction {
  label: string
  prompt: string
}

interface InputBarProps {
  /** 与 ``key`` 配合：欢迎区一键填入时递增 ``key`` 并传入本字段以重置输入框初值。 */
  initialText?: string
  placeholder?: string
  disabled?: boolean
  /** 流式生成中：显示「停止」并调用 ``onStop``（PRD 中区流式 SSE）。 */
  sending?: boolean
  onStop?: () => void
  onSend: (text: string, fileIds: string[]) => void
  onUpload?: (file: File) => Promise<string | undefined>
  /** From Agent ``ui_config.attachments`` (docs/39). */
  attachmentPolicy?: AttachmentPolicy
  onAttachmentRejected?: (message: string) => void
  /** ``ui_config.quick_actions`` (prd.md §4.5.4). */
  quickActions?: QuickAction[]
}

export default function InputBar({
  initialText = '',
  placeholder,
  disabled,
  sending = false,
  onStop,
  onSend,
  onUpload,
  attachmentPolicy,
  onAttachmentRejected,
  quickActions,
}: InputBarProps) {
  const [input, setInput] = useState(initialText)
  const [fileIds, setFileIds] = useState<string[]>([])
  const fileRef = useRef<HTMLInputElement>(null)

  const handleSend = () => {
    const text = input.trim()
    if ((!text && fileIds.length === 0) || disabled || sending) return
    onSend(text || '请根据附件内容处理。', fileIds)
    setInput('')
    setFileIds([])
  }

  const uploadAllowed = isAttachmentUploadAllowed(attachmentPolicy)
  const acceptAttr = attachmentInputAccept(attachmentPolicy)

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !onUpload || !uploadAllowed) return
    const check = await validateLocalAttachment(file, attachmentPolicy)
    if (!check.ok) {
      onAttachmentRejected?.(check.message)
      e.target.value = ''
      return
    }
    const id = await onUpload(file)
    if (id) setFileIds((prev) => [...prev, id])
    e.target.value = ''
  }

  return (
    <div className="px-4 py-3 border-t border-slate-200/80 bg-[var(--widget-surface)] safe-pb">
      {quickActions && quickActions.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {quickActions.map((q) => (
            <button
              key={q.label}
              type="button"
              disabled={disabled || sending}
              className="text-xs px-3 py-1.5 rounded-full border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 hover:border-slate-300 disabled:opacity-50 transition-colors"
              onClick={() => {
                setInput(q.prompt)
              }}
            >
              {q.label}
            </button>
          ))}
        </div>
      )}
      {fileIds.length > 0 && (
        <div className="flex gap-2 mb-2">
          {fileIds.map((id) => (
            <span key={id} className="text-xs px-2 py-1 bg-gray-100 rounded">
              附件 {id.slice(0, 8)}
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-2 items-center">
        {onUpload && uploadAllowed && (
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={disabled || sending}
            className="shrink-0 px-3 py-2.5 border border-slate-200 rounded-xl text-sm bg-white hover:bg-slate-50 disabled:opacity-50 shadow-sm"
            title="上传文件"
          >
            <span className="sr-only">上传文件</span>
            <svg className="w-5 h-5 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
            </svg>
          </button>
        )}
        <input
          type="file"
          ref={fileRef}
          className="hidden"
          accept={acceptAttr}
          onChange={handleFile}
        />
        <input
          type="text"
          className="flex-1 min-w-0 border border-slate-200 rounded-xl px-4 py-2.5 text-sm bg-white shadow-inner focus:outline-none focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500"
          placeholder={placeholder || '请输入...'}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          disabled={disabled}
        />
        {sending && onStop ? (
          <button
            type="button"
            onClick={onStop}
            className="shrink-0 bg-slate-800 text-white px-4 py-2.5 rounded-xl text-sm font-medium hover:bg-slate-900 shadow-sm"
          >
            停止
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSend}
            disabled={disabled || (!input.trim() && fileIds.length === 0)}
            className="shrink-0 bg-primary-600 text-white px-5 py-2.5 rounded-xl text-sm font-medium disabled:opacity-50 shadow-sm hover:bg-primary-700"
          >
            发送
          </button>
        )}
      </div>
    </div>
  )
}
