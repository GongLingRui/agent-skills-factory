interface ThinkingBlockProps {
  text: string
  stepCount?: number
}

export default function ThinkingBlock({ text, stepCount }: ThinkingBlockProps) {
  return (
    <details className="group rounded-lg border border-violet-200/80 bg-violet-50/90 text-violet-950 dark:border-violet-800/80 dark:bg-violet-950/40 dark:text-violet-100">
      <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium list-none flex items-center gap-2 [&::-webkit-details-marker]:hidden">
        <span className="text-violet-600 dark:text-violet-300">▸</span>
        模型推理过程
        {typeof stepCount === 'number' && (
          <span className="text-[10px] font-normal text-violet-600/90 dark:text-violet-300/80">
            ({stepCount} 段)
          </span>
        )}
        <span className="ml-auto text-[10px] font-normal text-violet-600/90 dark:text-violet-300/80">
          点击展开
        </span>
      </summary>
      <div className="border-t border-violet-200/70 dark:border-violet-800/60 px-3 py-2 space-y-2 max-h-64 overflow-y-auto text-xs leading-relaxed whitespace-pre-wrap text-violet-900/95 dark:text-violet-100/95">
        {text}
      </div>
    </details>
  )
}
