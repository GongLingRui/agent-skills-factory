import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
  exchangeToken,
  createSession,
  devBootstrapSession,
  heartbeat,
  fetchSessionMe,
} from '@/api/auth'
import {
  getModelCatalog,
  initSession,
  getAgent,
  type AgentDetail,
  type ModelCatalogItem,
} from '@/api/agents'
import { useSessionStore } from '@/stores/useSessionStore'
import { HEARTBEAT_INTERVAL_MS, MAX_HEARTBEAT_FAILURES } from '@/config/constants'
import { sendFrontendMetricBeacon } from '@/lib/metricsBeacon'
import { purgeExpiredChatHistory } from '@/lib/historyBackup'

const SESSIONS_RAIL_KEY = 'widget_local_sessions_rail_collapsed'

function widgetModelPrefKey(agentId: string) {
  return `af:widget_model_pref:${agentId}`
}

export function useChatSession(agentId: string | undefined, token: string | null) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { sessionId, setSession, clear } = useSessionStore()

  const [agent, setAgent] = useState<AgentDetail | null>(null)
  const [error, setError] = useState('')
  const [banner, setBanner] = useState('')
  const [modelCatalogItems, setModelCatalogItems] = useState<ModelCatalogItem[]>([])
  const [modelCatalogReady, setModelCatalogReady] = useState(false)
  const [preferredModelId, setPreferredModelId] = useState('')
  const [userHint, setUserHint] = useState('')
  const [department, setDepartment] = useState('')
  const [userIdHash, setUserIdHash] = useState<string | null>(null)
  const [sessionPermissions, setSessionPermissions] = useState<string[]>([])
  const [sessionAuthOk, setSessionAuthOk] = useState(false)
  const [historyRailCollapsed, setHistoryRailCollapsed] = useState(
    () =>
      typeof localStorage !== 'undefined' &&
      localStorage.getItem(SESSIONS_RAIL_KEY) === '1',
  )

  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const heartbeatFails = useRef(0)
  const metricsReadySent = useRef(false)
  const uiRenderMetricSent = useRef(false)

  useEffect(() => {
    void purgeExpiredChatHistory()
  }, [])

  useEffect(() => {
    if (typeof localStorage === 'undefined') return
    localStorage.setItem(SESSIONS_RAIL_KEY, historyRailCollapsed ? '1' : '0')
  }, [historyRailCollapsed])

  useEffect(() => {
    if (!sessionId) {
      setSessionAuthOk(false)
      return
    }
    setSessionAuthOk(false)
    void (async () => {
      try {
        const me = await fetchSessionMe()
        setUserHint(me.user_id_hint || '')
        setDepartment(me.department || '')
        setUserIdHash(me.user_id_hash || null)
        setSessionPermissions(me.permissions ?? [])
        setSessionAuthOk(true)
      } catch {
        setUserHint('')
        setDepartment('')
        setSessionPermissions([])
        setSessionAuthOk(false)
      }
    })()
  }, [sessionId])

  useEffect(() => {
    if (!sessionId || !sessionAuthOk) return
    heartbeatRef.current = setInterval(async () => {
      try {
        await heartbeat()
        heartbeatFails.current = 0
      } catch {
        heartbeatFails.current += 1
        if (heartbeatFails.current >= MAX_HEARTBEAT_FAILURES) {
          setError('网络异常，会话可能已过期')
        }
      }
    }, HEARTBEAT_INTERVAL_MS)
    return () => {
      if (heartbeatRef.current) clearInterval(heartbeatRef.current)
    }
  }, [sessionId, sessionAuthOk])

  useEffect(() => {
    if (!sessionId || !agentId || metricsReadySent.current) return
    metricsReadySent.current = true
    sendFrontendMetricBeacon({ agentId, eventType: 'widget_session_ready' })
  }, [sessionId, agentId])

  useEffect(() => {
    const uiConfig = agent?.ui_config as Record<string, unknown> | undefined
    if (!sessionId || !agentId || !uiConfig || uiRenderMetricSent.current) return
    uiRenderMetricSent.current = true
    sendFrontendMetricBeacon({ agentId, eventType: 'ui_config_render_ok' })
  }, [sessionId, agentId, agent])

  useEffect(() => {
    if (!agentId) return
    let cancelled = false
    setModelCatalogItems([])
    setModelCatalogReady(false)
    setPreferredModelId('')

    async function bootstrap() {
      try {
        if (token) {
          const ex = await exchangeToken(agentId!, token)
          const next = new URLSearchParams(searchParams)
          next.delete('token')
          navigate({ search: next.toString() }, { replace: true })
          await createSession(ex.token)
        } else if (
          !sessionId &&
          import.meta.env.VITE_DEV_WIDGET_AUTH_BYPASS === 'true'
        ) {
          await devBootstrapSession(agentId!)
        }

        const a = await getAgent(agentId!)
        if (cancelled) return
        setAgent(a)

        let catalogModels: ModelCatalogItem[] = []
        try {
          const cat = await getModelCatalog()
          if (cancelled) return
          catalogModels = cat.models
          setModelCatalogItems(cat.models)
        } catch {
          if (!cancelled) setModelCatalogItems([])
        } finally {
          if (!cancelled) setModelCatalogReady(true)
        }
        if (cancelled) return

        const prefRaw =
          typeof localStorage !== 'undefined'
            ? localStorage.getItem(widgetModelPrefKey(agentId!))
            : null
        const trimmed = prefRaw?.trim() ?? ''
        let effPref = ''
        if (trimmed && catalogModels.some((m) => m.id === trimmed)) {
          effPref = trimmed
        } else if (trimmed && typeof localStorage !== 'undefined') {
          localStorage.removeItem(widgetModelPrefKey(agentId!))
        }
        if (!cancelled) setPreferredModelId(effPref)

        const initModelOpt = effPref ? { model: effPref } : undefined

        if (token) {
          const init = await initSession(agentId!, undefined, initModelOpt)
          if (cancelled) return
          setSession({
            sessionId: init.session_id,
            runId: init.run_id,
            agentId: agentId!,
            uiConfig: init.ui_config,
            runtimeModel: init.runtime_model ?? null,
          })
          if (init.degradation?.hint) setBanner(init.degradation.hint)
        } else if (sessionId) {
          const init = await initSession(agentId!, sessionId, initModelOpt)
          if (cancelled) return
          setSession({
            sessionId: init.session_id,
            runId: init.run_id,
            agentId: agentId!,
            uiConfig: init.ui_config,
            runtimeModel: init.runtime_model ?? null,
          })
          if (init.degradation?.hint) setBanner(init.degradation.hint)
        } else if (import.meta.env.VITE_DEV_WIDGET_AUTH_BYPASS === 'true') {
          const init = await initSession(agentId!, undefined, initModelOpt)
          if (cancelled) return
          setSession({
            sessionId: init.session_id,
            runId: init.run_id,
            agentId: agentId!,
            uiConfig: init.ui_config,
            runtimeModel: init.runtime_model ?? null,
          })
          if (init.degradation?.hint) setBanner(init.degradation.hint)
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : '初始化失败'
        if (!cancelled) setError(msg)
      }
    }

    bootstrap()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, token])

  const handlePreferredModelChange = useCallback(
    async (value: string) => {
      if (!agentId || value === preferredModelId) return
      setError('')
      if (typeof localStorage !== 'undefined') {
        if (!value) {
          localStorage.removeItem(widgetModelPrefKey(agentId))
        } else {
          localStorage.setItem(widgetModelPrefKey(agentId), value)
        }
      }
      setPreferredModelId(value)
      clear()
      try {
        const init = await initSession(
          agentId,
          undefined,
          value ? { model: value } : undefined,
        )
        setSession({
          sessionId: init.session_id,
          runId: init.run_id,
          agentId,
          uiConfig: init.ui_config,
          runtimeModel: init.runtime_model ?? null,
        })
        if (init.degradation?.hint) {
          setBanner(init.degradation.hint)
        } else {
          setBanner('')
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : '切换模型失败')
      }
    },
    [agentId, preferredModelId, clear, setSession],
  )

  const handleNewChat = useCallback(async () => {
    if (!agentId) return
    setError('')
    clear()
    try {
      const init = await initSession(
        agentId,
        undefined,
        preferredModelId ? { model: preferredModelId } : undefined,
      )
      setSession({
        sessionId: init.session_id,
        runId: init.run_id,
        agentId,
        uiConfig: init.ui_config,
        runtimeModel: init.runtime_model ?? null,
      })
      if (init.degradation?.hint) {
        setBanner(init.degradation.hint)
      } else {
        setBanner('')
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '无法开启新对话')
    }
  }, [agentId, preferredModelId, clear, setSession])

  return {
    agent,
    error,
    setError,
    banner,
    setBanner,
    modelCatalogItems,
    modelCatalogReady,
    preferredModelId,
    setPreferredModelId,
    userHint,
    department,
    userIdHash,
    sessionPermissions,
    sessionAuthOk,
    historyRailCollapsed,
    setHistoryRailCollapsed,
    handlePreferredModelChange,
    handleNewChat,
  }
}
