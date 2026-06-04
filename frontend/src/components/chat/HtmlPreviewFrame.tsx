import { useMemo, useState } from 'react'
import { isCompleteHtmlDocument, prepareHtmlDocument } from '@/lib/htmlPreview'

interface HtmlPreviewFrameProps {
  html: string
  /** Shorter label when showing a single segment inside a message. */
  label?: string
  defaultShowSource?: boolean
  /** Sticky deck bar uses a compact viewport; inline message preview is taller. */
  size?: 'inline' | 'deck'
}

const PREVIEW_HEIGHT: Record<'inline' | 'deck', string> = {
  inline: 'min(48vh, 520px)',
  deck: 'min(32vh, 360px)',
}

export default function HtmlPreviewFrame({
  html,
  label = 'HTML 预览',
  defaultShowSource = false,
  size = 'inline',
}: HtmlPreviewFrameProps) {
  const [showSource, setShowSource] = useState(defaultShowSource)
  const doc = useMemo(() => prepareHtmlDocument(html), [html])
  const complete = isCompleteHtmlDocument(doc)

  const download = () => {
    const blob = new Blob([doc], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'presentation.html'
    a.click()
    URL.revokeObjectURL(url)
  }

  const openTab = () => {
    const blob = new Blob([doc], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener,noreferrer')
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }

  return (
    <div className="rounded-xl border border-slate-200/90 dark:border-slate-600 overflow-hidden bg-slate-50 dark:bg-slate-900/40">
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b border-slate-200/80 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
            {label}
          </span>
          {!complete && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-900 dark:bg-amber-950/60 dark:text-amber-100">
              片段（回复「继续」后可拼接完整预览）
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-1">
          <button
            type="button"
            onClick={() => setShowSource((v) => !v)}
            className="text-[11px] px-2 py-1 rounded-md border border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700"
          >
            {showSource ? '看预览' : '看源码'}
          </button>
          <button
            type="button"
            onClick={download}
            className="text-[11px] px-2 py-1 rounded-md border border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700"
          >
            下载 .html
          </button>
          <button
            type="button"
            onClick={openTab}
            className="text-[11px] px-2 py-1 rounded-md bg-primary-600 text-white hover:bg-primary-700"
          >
            新窗口打开
          </button>
        </div>
      </div>
      {showSource ? (
        <pre
          className="overflow-auto p-3 text-[11px] leading-relaxed font-mono bg-slate-950 text-slate-100"
          style={{ maxHeight: PREVIEW_HEIGHT[size] }}
        >
          {html}
        </pre>
      ) : (
        <iframe
          title={label}
          sandbox="allow-scripts allow-popups"
          srcDoc={doc}
          className="w-full bg-white dark:bg-slate-950 border-0"
          style={{ height: PREVIEW_HEIGHT[size] }}
        />
      )}
    </div>
  )
}
