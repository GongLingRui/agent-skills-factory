import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { useSessionStore } from '@/stores/useSessionStore'
import { useChatStore } from '@/stores/useChatStore'
import { useAgentStore } from '@/stores/useAgentStore'
import { useChatSession } from '@/hooks/useChatSession'
import { useChatStream } from '@/hooks/useChatStream'
import { useChatHistory } from '@/hooks/useChatHistory'
import { uploadFile } from '@/api/upload'
import { initSession } from '@/api/agents'
import { db } from '@/db/index'
import {
  clearWidgetCryptoKeyCache,
  ensureWidgetCryptoKey,
  isLocalEncryptionEnabled,
  migrateAllHistoriesToCipher,
  migrateAllHistoriesToPlain,
  setLocalEncryptionEnabled,
} from '@/lib/chatHistorySecure'
import { canUseSubtleCrypto } from '@/lib/localCrypto'
import {
  extractHtmlSegmentsFromText,
  mergeHtmlDeckSegments,
} from '@/lib/htmlPreview'
import FavoritesReorderModal from '@/components/layout/FavoritesReorderModal'
import Header from '@/components/layout/Header'
import BrowserCompatBanner from '@/components/layout/BrowserCompatBanner'
import HistorySidebar from '@/components/layout/HistorySidebar'
import PrivacySettingsModal from '@/components/layout/PrivacySettingsModal'
import UsageWarningBar from '@/components/layout/UsageWarningBar'
import MessageList from '@/components/chat/MessageList'
import HtmlDeckPreview from '@/components/chat/HtmlDeckPreview'
import InputBar from '@/components/layout/InputBar'
import type { AttachmentPolicy } from '@/lib/attachmentPolicy'

const CLEAR_ON_EXIT_KEY = 'widget_clear_on_exit'

function canOpenRegistryOps(permissions: string[] | undefined): boolean {
  return Boolean(
    permissions?.some((p) => p === 'agent.write' || p === 'agent.admin'),
  )
}

function readQuickActions(
  ui: Record<string, unknown> | undefined,
  agentUi: Record<string, unknown> | undefined,
): Array<{ label: string; prompt: string }> | undefined {
  const raw = ui?.quick_actions ?? agentUi?.quick_actions
  if (!Array.isArray(raw)) return undefined
  const out: Array<{ label: string; prompt: string }> = []
  for (const item of raw) {
    if (
      item &&
      typeof item === 'object' &&
      'label' in item &&
      'prompt' in item &&
      typeof (item as { label: unknown }).label === 'string' &&
      typeof (item as { prompt: unknown }).prompt === 'string'
    ) {
      out.push({
        label: (item as { label: string }).label,
        prompt: (item as { prompt: string }).prompt,
      })
    }
  }
  return out.length ? out : undefined
}

export default function ChatPage() {
  const { agentId } = useParams<{ agentId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token')

  const { sessionId, runId, uiConfig, setSession, clear } = useSessionStore()
  const { messages, setMessages, reset } = useChatStore()
  const {
    agents,
    favorites,
    recents,
    recentAt,
    loadAgents,
    setCurrentAgent,
    toggleFavorite,
    moveFavorite,
    setFavoriteOrder,
  } = useAgentStore()

  const {
    agent,
    error,
    setError,
    banner,
    setBanner,
    modelCatalogItems,
    modelCatalogReady,
    preferredModelId,
    userHint,
    department,
    userIdHash,
    sessionPermissions,
    historyRailCollapsed,
    setHistoryRailCollapsed,
    handlePreferredModelChange,
    handleNewChat,
  } = useChatSession(agentId, token)

  const { sending, send, handleStop, connectionState } = useChatStream()
  const { loadHistory } = useChatHistory(agentId, sessionId, null)

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [favReorderOpen, setFavReorderOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [composerSlot, setComposerSlot] = useState({ key: 0, text: '' })
  const [, setUsageHint] = useState('')
  const [warningEvent, setWarningEvent] = useState<{ code: string; message: string } | null>(null)
  const [clearOnExit, setClearOnExit] = useState(
    () =>
      typeof localStorage !== 'undefined' &&
      localStorage.getItem(CLEAR_ON_EXIT_KEY) === '1',
  )
  const [localEncryption, setLocalEncryption] = useState(isLocalEncryptionEnabled())
  const [cryptoKey, setCryptoKey] = useState<CryptoKey | null>(null)
  const [cryptoUnsupported] = useState(
    () => typeof globalThis !== 'undefined' && !canUseSubtleCrypto(),
  )

  useEffect(() => {
    const fn = () => {
      if (
        typeof localStorage !== 'undefined' &&
        localStorage.getItem(CLEAR_ON_EXIT_KEY) === '1'
      ) {
        void db.history.clear()
      }
    }
    window.addEventListener('beforeunload', fn)
    return () => window.removeEventListener('beforeunload', fn)
  }, [])

  useEffect(() => {
    if (!agentId) return
    void loadAgents()
    setCurrentAgent(agentId)
  }, [agentId, loadAgents, setCurrentAgent])

  useEffect(() => {
    let cancelled = false
    if (!localEncryption || !userIdHash) {
      queueMicrotask(() => {
        if (!cancelled) setCryptoKey(null)
      })
      return () => { cancelled = true }
    }
    void ensureWidgetCryptoKey(userIdHash)
      .then((k) => { if (!cancelled) setCryptoKey(k) })
      .catch(() => { if (!cancelled) setCryptoKey(null) })
    return () => { cancelled = true }
  }, [localEncryption, userIdHash])

  const handleSend = useCallback(
    async (text: string, fileIds: string[]) => {
      if (!agentId || !sessionId) return
      setError('')
      setUsageHint('')
      setWarningEvent(null)
      await send(agentId, sessionId, text, fileIds, (msg) => setError(msg))
    },
    [agentId, sessionId, send, setError],
  )

  const applyQuickPrompt = useCallback((text: string) => {
    setComposerSlot((s) => ({ key: s.key + 1, text }))
  }, [])

  const handleUpload = useCallback(
    async (file: File) => {
      if (!agentId) return undefined
      try {
        const res = await uploadFile(agentId, file)
        return res.file_id
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e)
        setError(`上传失败: ${msg}`)
        return undefined
      }
    },
    [agentId],
  )

  const handleSwitchAgent = useCallback(
    (id: string) => {
      if (id && id !== agentId) {
        clear()
        reset()
        navigate(`/apps/${id}`)
      }
    },
    [agentId, clear, reset, navigate],
  )

  const handlePickHistorySession = useCallback(
    async (sid: string) => {
      if (!agentId) return
      setError('')
      reset()
      try {
        const init = await initSession(
          agentId,
          sid,
          preferredModelId ? { model: preferredModelId } : undefined,
        )
        setSession({
          sessionId: init.session_id,
          runId: init.run_id,
          agentId,
          uiConfig: init.ui_config,
          runtimeModel: init.runtime_model ?? null,
        })
        if (init.degradation?.hint) setBanner(init.degradation.hint)
        const restored = await loadHistory(sid)
        if (restored.length) {
          setMessages(restored)
        } else {
          setMessages([])
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : '加载历史失败')
      }
    },
    [agentId, preferredModelId, reset, setSession, setMessages, loadHistory],
  )

  const handleCloseWidget = useCallback(() => {
    window.close()
  }, [])

  const toggleClearOnExit = useCallback(() => {
    setClearOnExit((v) => {
      const next = !v
      if (typeof localStorage !== 'undefined') {
        if (next) localStorage.setItem(CLEAR_ON_EXIT_KEY, '1')
        else localStorage.removeItem(CLEAR_ON_EXIT_KEY)
      }
      return next
    })
  }, [])

  const toggleLocalEncryption = useCallback(async () => {
    const next = !localEncryption
    if (!next) {
      try {
        const k =
          cryptoKey ||
          (userIdHash ? await ensureWidgetCryptoKey(userIdHash) : null)
        if (k) await migrateAllHistoriesToPlain(k)
      } catch { /* best-effort decrypt */ }
      clearWidgetCryptoKeyCache()
      setLocalEncryptionEnabled(false)
      setLocalEncryption(false)
      setCryptoKey(null)
      return
    }
    if (cryptoUnsupported) {
      window.alert('当前环境不支持 SubtleCrypto，无法启用本地加密')
      return
    }
    if (!userIdHash) {
      window.alert('请先完成会话初始化后再启用本地加密')
      return
    }
    try {
      const k = await ensureWidgetCryptoKey(userIdHash)
      await migrateAllHistoriesToCipher(k)
      setLocalEncryptionEnabled(true)
      setLocalEncryption(true)
      setCryptoKey(k)
    } catch (e: unknown) {
      window.alert(e instanceof Error ? e.message : '启用本地加密失败')
    }
  }, [localEncryption, cryptoKey, userIdHash, cryptoUnsupported])

  const welcome =
    (uiConfig?.welcome_message as string) ||
    (agent?.ui_config?.welcome_message as string) ||
    '您好，有什么可以帮您？'
  const title = (uiConfig?.title as string) || agent?.name || 'Agent'
  const avatar =
    (uiConfig?.avatar as string) ||
    (agent?.ui_config?.avatar as string)
  const placeholder = (uiConfig?.input_placeholder as string) || '请输入...'
  const quickActions = readQuickActions(
    uiConfig,
    agent?.ui_config as Record<string, unknown> | undefined,
  )
  const feedbackCtx =
    sessionId && runId && agentId
      ? { sessionId, runId, agentId }
      : undefined

  const buildLabel =
    typeof import.meta.env.VITE_WIDGET_BUILD_LABEL === 'string'
      ? import.meta.env.VITE_WIDGET_BUILD_LABEL
      : import.meta.env.MODE === 'development'
        ? 'dev'
        : undefined

  const modelSelectOptions = useMemo(() => {
    const opts = [{ value: '', label: '默认（Agent 配置）' }]
    for (const m of modelCatalogItems) {
      const suffix = m.endpoint_host ? ` · ${m.endpoint_host}` : ''
      const raw = `${m.id}${suffix}`
      opts.push({
        value: m.id,
        label: raw.length > 80 ? `${raw.slice(0, 77)}...` : raw,
      })
    }
    return opts
  }, [modelCatalogItems])

  const attachmentPolicy: AttachmentPolicy | undefined =
    (uiConfig?.attachments && typeof uiConfig.attachments === 'object'
      ? uiConfig.attachments
      : undefined) ??
    (agent?.ui_config?.attachments &&
    typeof agent.ui_config.attachments === 'object'
      ? agent.ui_config.attachments
      : undefined)

  const htmlDetectedInChat = useMemo(
    () =>
      messages.some(
        (m) =>
          m.role === 'assistant' &&
          extractHtmlSegmentsFromText(m.content).length > 0,
      ),
    [messages],
  )

  const htmlPreviewEnabled =
    uiConfig?.render_html_preview === true ||
    (agent?.ui_config as Record<string, unknown> | undefined)
      ?.render_html_preview === true ||
    agentId === 'business-presentation-generator-agent' ||
    htmlDetectedInChat

  const htmlDeckSegments = useMemo(() => {
    if (!htmlPreviewEnabled) return []
    const parts: string[] = []
    for (const msg of messages) {
      if (msg.role !== 'assistant') continue
      parts.push(...extractHtmlSegmentsFromText(msg.content))
    }
    return parts
  }, [htmlPreviewEnabled, messages])

  const mergedHtmlDeck = useMemo(
    () => mergeHtmlDeckSegments(htmlDeckSegments),
    [htmlDeckSegments],
  )

  const assistantHtmlMessageCount = useMemo(
    () =>
      messages.filter(
        (m) =>
          m.role === 'assistant' &&
          extractHtmlSegmentsFromText(m.content).length > 0,
      ).length,
    [messages],
  )

  const showDeckPreview =
    htmlPreviewEnabled &&
    mergedHtmlDeck.trim().length > 0 &&
    (htmlDeckSegments.length > 1 || assistantHtmlMessageCount > 1)

  const htmlPreviewInline = htmlPreviewEnabled && !showDeckPreview

  return (
    <div className="flex h-[100dvh] bg-[var(--widget-bg)] text-slate-900 dark:text-slate-100 overflow-hidden">
      {agentId && (
        <HistorySidebar
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          agentId={agentId}
          currentSessionId={sessionId}
          onPickSession={handlePickHistorySession}
          decryptKey={localEncryption ? cryptoKey : null}
          localEncryption={localEncryption}
          desktopCollapsed={historyRailCollapsed}
          onDesktopCollapsedChange={setHistoryRailCollapsed}
          onAfterImport={async () => {
            if (!localEncryption || !userIdHash) return
            const k = await ensureWidgetCryptoKey(userIdHash)
            await migrateAllHistoriesToCipher(k)
          }}
        />
      )}
      <div className="flex-1 flex flex-col min-w-0 min-h-0 dark:text-slate-100">
        <BrowserCompatBanner />
        {banner && (
          <div className="shrink-0 px-4 py-2.5 bg-amber-50/95 dark:bg-amber-950/50 text-amber-950 dark:text-amber-50 text-sm border-b border-amber-100/80 dark:border-amber-800/80 backdrop-blur-sm">
            <p className="leading-snug">{banner}</p>
          </div>
        )}
        <UsageWarningBar
          warning={warningEvent}
          onNewChat={sessionId ? () => void handleNewChat() : undefined}
        />
        {connectionState === 'reconnecting' && (
          <div className="shrink-0 px-4 py-2 bg-blue-50 dark:bg-blue-950/40 text-blue-800 dark:text-blue-100 text-xs border-b border-blue-100 dark:border-blue-800/60 flex items-center gap-2">
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-600" />
            </span>
            连接中断，正在重连…
          </div>
        )}
        {connectionState === 'disconnected' && !sending && (
          <div className="shrink-0 px-4 py-2 bg-slate-100 dark:bg-slate-800/60 text-slate-600 dark:text-slate-300 text-xs border-b border-slate-200 dark:border-slate-700 flex items-center gap-2">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.5 0L4.206 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            连接已断开
          </div>
        )}
        <Header
          title={title}
          avatar={avatar}
          agents={agents}
          favoriteIds={favorites}
          recentIds={recents}
          recentAt={recentAt}
          currentAgentId={agentId || null}
          onSwitchAgent={handleSwitchAgent}
          onToggleFavorite={
            agentId ? () => toggleFavorite(agentId) : undefined
          }
          isFavorite={agentId ? favorites.includes(agentId) : false}
          onMoveFavorite={
            agentId && favorites.includes(agentId)
              ? (dir) => moveFavorite(agentId, dir)
              : undefined
          }
          userHint={userHint}
          department={department}
          hideHistoryOnLargeScreen={!historyRailCollapsed}
          onOpenHistory={() => setSidebarOpen(true)}
          onCloseWidget={handleCloseWidget}
          onOpenApps={() => navigate('/apps')}
          onOpenRegistry={
            sessionId && canOpenRegistryOps(sessionPermissions)
              ? () => navigate('/admin/agents')
              : undefined
          }
          onOpenFavoriteReorder={
            favorites.length > 0 ? () => setFavReorderOpen(true) : undefined
          }
          onNewChat={sessionId ? handleNewChat : undefined}
          onOpenAbout={
            agentId ? () => navigate(`/apps/${agentId}/about`) : undefined
          }
          onOpenSettings={() => setSettingsOpen(true)}
          buildLabel={buildLabel}
          modelSelect={
            modelCatalogReady && agentId
              ? {
                  value: preferredModelId,
                  options: modelSelectOptions,
                  onChange: (v: string) => void handlePreferredModelChange(v),
                  disabled: !sessionId || sending,
                  loading: false,
                }
              : undefined
          }
        />
        {showDeckPreview && <HtmlDeckPreview segments={htmlDeckSegments} />}
        <MessageList
          messages={messages}
          welcome={welcome}
          agentTitle={title}
          agentAvatar={avatar}
          quickActions={quickActions}
          onApplyQuickPrompt={applyQuickPrompt}
          sending={sending}
          feedbackContext={feedbackCtx}
          htmlPreviewEnabled={htmlPreviewInline}
          htmlInDeckPreview={showDeckPreview}
        />
        {error && (
          <div className="shrink-0 px-4 py-2.5 bg-red-50 text-red-800 text-sm border-t border-red-100">
            {error}
          </div>
        )}
        <InputBar
          key={composerSlot.key}
          initialText={composerSlot.text}
          placeholder={placeholder}
          disabled={sending || !sessionId}
          sending={sending}
          onStop={handleStop}
          onSend={handleSend}
          onUpload={handleUpload}
          attachmentPolicy={attachmentPolicy}
          onAttachmentRejected={(m) => setError(m)}
          quickActions={quickActions}
        />
      </div>
      <PrivacySettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        clearOnExit={clearOnExit}
        onToggleClearOnExit={toggleClearOnExit}
        localEncryption={localEncryption}
        onToggleLocalEncryption={toggleLocalEncryption}
        cryptoUnsupported={cryptoUnsupported}
        encryptionKeyPending={Boolean(
          localEncryption && userIdHash && !cryptoKey,
        )}
      />
      <FavoritesReorderModal
        open={favReorderOpen}
        onClose={() => setFavReorderOpen(false)}
        favoriteIds={favorites}
        agents={agents}
        onSave={(ids: string[]) => setFavoriteOrder(ids)}
      />
    </div>
  )
}
