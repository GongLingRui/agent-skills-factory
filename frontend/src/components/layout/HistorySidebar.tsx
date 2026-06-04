import { useCallback, useEffect, useState, type ChangeEventHandler } from 'react'
import { db, type ChatHistory } from '@/db'
import { revealChatHistory } from '@/lib/chatHistorySecure'
import { exportHistoriesJson, importHistoriesJson } from '@/lib/historyBackup'

interface HistorySidebarProps {
  /** 移动端抽屉是否打开。 */
  open: boolean
  onClose: () => void
  agentId: string
  currentSessionId: string | null
  onPickSession: (sessionId: string) => void
  decryptKey?: CryptoKey | null
  localEncryption?: boolean
  onAfterImport?: () => void | Promise<void>
  /** 桌面端：本地会话栏是否折叠为窄条。 */
  desktopCollapsed: boolean
  onDesktopCollapsedChange: (collapsed: boolean) => void
}

function ChevronLeftIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
    </svg>
  )
}

function ChevronRightIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
    </svg>
  )
}

function HistoryChrome({
  rows,
  currentSessionId,
  onPickSession,
  onClose,
  agentId,
  decryptKey,
  localEncryption,
  onAfterImport,
  onReload,
  desktop,
  onCollapseDesktop,
}: {
  rows: ChatHistory[]
  currentSessionId: string | null
  onPickSession: (sessionId: string) => void
  onClose: () => void
  agentId: string
  decryptKey?: CryptoKey | null
  localEncryption?: boolean
  onAfterImport?: () => void | Promise<void>
  onReload: () => Promise<void>
  desktop?: boolean
  onCollapseDesktop?: () => void
}) {
  const handleExport = async () => {
    if (localEncryption && !decryptKey) {
      window.alert('本地加密已开启但密钥未就绪，请稍后重试导出')
      return
    }
    const blob = new Blob([await exportHistoriesJson(decryptKey)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `agent-factory-chat-backup-${agentId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleImport: ChangeEventHandler<HTMLInputElement> = async (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    try {
      const n = await importHistoriesJson(await f.text())
      await onAfterImport?.()
      await onReload()
      window.alert(`已导入 ${n} 条本地记录`)
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '导入失败')
    }
  }

  return (
    <>
      <div className="px-3 py-3 border-b border-slate-200/80 flex justify-between items-center bg-slate-50/50 gap-2">
        <span className="font-semibold text-sm text-slate-800 truncate">本地会话</span>
        <div className="flex items-center gap-1 shrink-0">
          {desktop && onCollapseDesktop && (
            <button
              type="button"
              className="p-1.5 rounded-lg text-slate-500 hover:bg-white hover:text-slate-800"
              aria-label="折叠侧栏"
              title="折叠侧栏"
              onClick={onCollapseDesktop}
            >
              <ChevronLeftIcon />
            </button>
          )}
          {!desktop && (
            <button
              type="button"
              className="text-sm text-slate-500 hover:text-slate-800 p-1 rounded-lg hover:bg-white"
              onClick={onClose}
            >
              关闭
            </button>
          )}
        </div>
      </div>
      <div className="px-3 py-2 border-b border-slate-200/80 flex gap-2 flex-wrap bg-white">
        <button
          type="button"
          className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700"
          onClick={() => void handleExport()}
        >
          导出 JSON
        </button>
        <label className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 cursor-pointer text-slate-700">
          导入
          <input type="file" accept="application/json" className="hidden" onChange={handleImport} />
        </label>
      </div>
      <ul className="flex-1 overflow-y-auto text-sm min-h-0">
        {rows.length === 0 && (
          <li className="px-4 py-8 text-center text-slate-500 text-sm">
            暂无保存的对话。发送消息后会在本机自动存档。
          </li>
        )}
        {rows.map((r) => (
          <li key={r.id}>
            <button
              type="button"
              className={`w-full text-left px-3 py-2.5 border-b border-slate-100 hover:bg-slate-50 transition-colors ${
                r.sessionId === currentSessionId ? 'bg-primary-50 border-l-2 border-l-primary-600' : ''
              }`}
              onClick={() => {
                onPickSession(r.sessionId)
                if (!desktop) onClose()
              }}
            >
              <div className="truncate font-medium text-slate-800">{r.title}</div>
              <div className="text-xs text-slate-400 truncate mt-0.5 font-mono">{r.sessionId}</div>
            </button>
          </li>
        ))}
      </ul>
    </>
  )
}

function DesktopCollapsedRail({ onExpand }: { onExpand: () => void }) {
  return (
    <div className="hidden lg:flex w-[3.25rem] shrink-0 flex-col items-center border-r border-slate-200/80 bg-[var(--widget-surface)] py-3 min-h-0">
      <button
        type="button"
        className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
        aria-label="展开本地会话"
        title="展开本地会话"
        onClick={onExpand}
      >
        <ChevronRightIcon />
      </button>
    </div>
  )
}

/**
 * PRD §4.5.4：侧栏本地历史 + 导入导出。桌面端可折叠；小屏为抽屉。
 */
export default function HistorySidebar({
  open,
  onClose,
  agentId,
  currentSessionId,
  onPickSession,
  decryptKey = null,
  localEncryption = false,
  onAfterImport,
  desktopCollapsed,
  onDesktopCollapsedChange,
}: HistorySidebarProps) {
  const [rows, setRows] = useState<ChatHistory[]>([])

  const reloadRows = useCallback(async () => {
    if (!agentId) return
    const list = await db.history.where('agentId').equals(agentId).toArray()
    list.sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime())
    const revealed = await Promise.all(
      list.map((r) => revealChatHistory(r, decryptKey)),
    )
    setRows(revealed)
  }, [agentId, decryptKey])

  useEffect(() => {
    const id = window.setTimeout(() => {
      void reloadRows()
    }, 0)
    return () => clearTimeout(id)
  }, [reloadRows, localEncryption, open])

  return (
    <>
      {desktopCollapsed ? (
        <DesktopCollapsedRail onExpand={() => onDesktopCollapsedChange(false)} />
      ) : (
        <aside className="hidden lg:flex w-72 shrink-0 border-r border-slate-200/80 bg-[var(--widget-surface)] flex-col h-full min-h-0">
          <HistoryChrome
            rows={rows}
            currentSessionId={currentSessionId}
            onPickSession={onPickSession}
            onClose={onClose}
            agentId={agentId}
            decryptKey={decryptKey}
            localEncryption={localEncryption}
            onAfterImport={onAfterImport}
            onReload={reloadRows}
            desktop
            onCollapseDesktop={() => onDesktopCollapsedChange(true)}
          />
        </aside>
      )}
      {open && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <button
            type="button"
            className="flex-1 bg-slate-900/35 backdrop-blur-[1px]"
            aria-label="关闭侧栏"
            onClick={onClose}
          />
          <aside className="w-[min(20rem,88vw)] shrink-0 bg-[var(--widget-surface)] border-l border-slate-200/80 shadow-2xl flex flex-col h-full min-h-0">
            <HistoryChrome
              rows={rows}
              currentSessionId={currentSessionId}
              onPickSession={onPickSession}
              onClose={onClose}
              agentId={agentId}
              decryptKey={decryptKey}
              localEncryption={localEncryption}
              onAfterImport={onAfterImport}
              onReload={reloadRows}
              desktop={false}
            />
          </aside>
        </div>
      )}
    </>
  )
}
