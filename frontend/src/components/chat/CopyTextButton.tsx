import { useCallback, useState } from 'react'

interface CopyTextButtonProps {
  text: string
  /** user: 深蓝气泡上的浅色按钮；assistant: 灰底区域上的默认样式 */
  variant: 'user' | 'assistant'
}

function IconClipboard({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function IconCheck({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

/** 复制整条消息原文（含 Markdown）；图标样式与点赞/点踩一致。 */
export default function CopyTextButton({ text, variant }: CopyTextButtonProps) {
  const [copied, setCopied] = useState(false)

  const onCopy = useCallback(async () => {
    const t = text.trim()
    if (!t) return
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      try {
        const ta = document.createElement('textarea')
        ta.value = text
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 2000)
      } catch {
        /* ignore */
      }
    }
  }, [text])

  const base =
    'inline-flex items-center justify-center w-8 h-8 shrink-0 rounded border ' +
    'transition-colors disabled:opacity-40 disabled:pointer-events-none'

  const cls =
    variant === 'user'
      ? `${base} border-white/35 text-white/95 hover:bg-white/15`
      : `${base} border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/80`

  return (
    <button
      type="button"
      className={cls}
      onClick={() => void onCopy()}
      disabled={!text.trim()}
      title={copied ? '已复制' : '复制全文'}
      aria-label={copied ? '已复制到剪贴板' : '复制全文'}
    >
      {copied ? (
        <IconCheck
          className={
            variant === 'user' ? 'text-emerald-300' : 'text-emerald-600 dark:text-emerald-400'
          }
        />
      ) : (
        <IconClipboard />
      )}
    </button>
  )
}
