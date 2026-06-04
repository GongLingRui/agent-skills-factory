import { create } from 'zustand'

interface SessionState {
  sessionId: string | null
  runId: string | null
  agentId: string | null
  uiConfig: Record<string, unknown>
  /** Resolved primary model id from last /init (RunSpec runtime.model). */
  runtimeModel: string | null
  setSession: (s: {
    sessionId: string
    runId: string
    agentId: string
    uiConfig: Record<string, unknown>
    runtimeModel?: string | null
  }) => void
  clear: () => void
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: null,
  runId: null,
  agentId: null,
  uiConfig: {},
  runtimeModel: null,
  setSession: (s) =>
    set({
      sessionId: s.sessionId,
      runId: s.runId,
      agentId: s.agentId,
      uiConfig: s.uiConfig,
      runtimeModel: s.runtimeModel ?? null,
    }),
  clear: () =>
    set({
      sessionId: null,
      runId: null,
      agentId: null,
      uiConfig: {},
      runtimeModel: null,
    }),
}))
