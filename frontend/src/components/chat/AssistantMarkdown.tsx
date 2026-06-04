import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

/**
 * Models often glue GFM table rows with ``||`` on one line; remark-gfm then
 * fails to parse a table. Split only ``||`` before separator rows or next
 * cell-like tokens (heuristic; may rarely touch non-table ``||``).
 */
function loosenPipeGluedTableRows(md: string): string {
  if (!/\|\|/.test(md)) return md
  return md
    .replace(/\|\|(?=-{2,})/g, '\n|')
    .replace(/\|\|(?=\s*["'|「])/g, '\n|')
}

const markdownComponents: Components = {
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-primary-600 underline underline-offset-2 hover:text-primary-700"
    >
      {children}
    </a>
  ),
  code: ({ className, children, ...props }) => {
    const inline = !className
    if (inline) {
      return (
        <code
          className="rounded bg-black/[0.06] px-1.5 py-0.5 font-mono text-[0.875em] text-gray-900"
          {...props}
        >
          {children}
        </code>
      )
    }
    return (
      <code className={className} {...props}>
        {children}
      </code>
    )
  },
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-md border border-slate-700 bg-slate-950 p-3 text-xs leading-relaxed text-slate-100">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-3 w-full max-w-full overflow-x-auto rounded-lg border border-slate-200 bg-white dark:border-slate-600 dark:bg-slate-900/40">
      <table className="min-w-full border-collapse text-left text-[13px] leading-snug">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-slate-50 dark:bg-slate-800/80">{children}</thead>
  ),
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr className="even:bg-slate-50/80 dark:even:bg-slate-800/40">{children}</tr>,
  th: ({ children }) => (
    <th className="border border-slate-200 px-3 py-2 font-semibold text-slate-900 dark:border-slate-600 dark:text-slate-100">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-slate-200 px-3 py-2 align-top text-slate-800 dark:border-slate-600 dark:text-slate-200">
      {children}
    </td>
  ),
}

interface AssistantMarkdownProps {
  children: string
}

/** Renders assistant copy as GitHub-flavored Markdown inside the chat bubble. */
export default function AssistantMarkdown({ children }: AssistantMarkdownProps) {
  return (
    <div
      className={
        'prose prose-sm max-w-none text-gray-900 prose-headings:text-gray-900 ' +
        'prose-headings:font-semibold prose-p:leading-relaxed prose-li:my-0.5 ' +
        'prose-ul:my-2 prose-ol:my-2 prose-strong:text-gray-900 ' +
        'prose-table:block prose-table:w-full ' +
        '[&>*:first-child]:mt-0 [&>*:last-child]:mb-0'
      }
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {loosenPipeGluedTableRows(children)}
      </ReactMarkdown>
    </div>
  )
}
