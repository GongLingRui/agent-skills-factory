import { useMemo, useState } from 'react'
import HtmlPreviewFrame from './HtmlPreviewFrame'
import {
  isCompleteHtmlDocument,
  mergeHtmlDeckSegments,
  prepareHtmlDocument,
} from '@/lib/htmlPreview'

interface HtmlDeckPreviewProps {
  segments: string[]
}

/** Sticky combined preview for multi-turn HTML slide generation. */
export default function HtmlDeckPreview({ segments }: HtmlDeckPreviewProps) {
  const [expanded, setExpanded] = useState(true)
  const merged = useMemo(() => mergeHtmlDeckSegments(segments), [segments])
  const doc = useMemo(() => prepareHtmlDocument(merged), [merged])
  if (!merged.trim()) return null

  const complete = isCompleteHtmlDocument(doc)
  const label = complete
    ? `幻灯片预览（已拼接 ${segments.length} 段）`
    : `幻灯片预览（${segments.length} 段，生成中…）`

  return (
    <div className="shrink-0 border-b border-slate-200/80 dark:border-slate-700 bg-[var(--widget-surface)]/95 backdrop-blur-sm px-3 sm:px-5 py-2">
      <div className="flex justify-end mb-1">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-[11px] px-2 py-1 rounded-md border border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700"
        >
          {expanded ? '收起预览' : '展开预览'}
        </button>
      </div>
      {expanded && (
        <HtmlPreviewFrame html={merged} label={label} size="deck" />
      )}
    </div>
  )
}
