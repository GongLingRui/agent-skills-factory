interface UsageWarningBarProps {
  warning: { code: string; message: string } | null
  onNewChat?: () => void
}

export default function UsageWarningBar({ warning, onNewChat }: UsageWarningBarProps) {
  if (!warning) return null
  return (
    <div className="shrink-0 px-4 py-2.5 bg-amber-50/95 dark:bg-amber-950/50 text-amber-950 dark:text-amber-50 text-sm border-b border-amber-100/80 dark:border-amber-800/80 backdrop-blur-sm flex flex-wrap items-center gap-3 justify-between">
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <svg
          className="shrink-0 h-4 w-4 text-amber-700 dark:text-amber-300"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
            clipRule="evenodd"
          />
        </svg>
        <p className="leading-snug text-amber-900/90 dark:text-amber-100/95">
          {warning.message}
        </p>
      </div>
      {onNewChat && (
        <button
          type="button"
          className="shrink-0 rounded-lg bg-amber-900 dark:bg-amber-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-950 dark:hover:bg-amber-600"
          onClick={onNewChat}
        >
          开启新会话
        </button>
      )}
    </div>
  )
}
