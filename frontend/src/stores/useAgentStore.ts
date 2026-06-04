import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { listAgents, type AgentItem } from '@/api/agents'
import { LOCAL_STORAGE_KEYS, MAX_FAVORITES, MAX_RECENTS } from '@/config/constants'

interface AgentState {
  agents: AgentItem[]
  currentAgentId: string | null
  favorites: string[]
  recents: string[]
  /** Last open time per agent id (ms) for PRD §4.5.6 “最近”. */
  recentAt: Record<string, number>
  loadAgents: () => Promise<void>
  setCurrentAgent: (id: string) => void
  toggleFavorite: (id: string) => void
  addRecent: (id: string) => void
  moveFavorite: (id: string, direction: -1 | 1) => void
  setFavoriteOrder: (ids: string[]) => void
}

export const useAgentStore = create<AgentState>()(
  persist(
    (set, get) => ({
      agents: [],
      currentAgentId: null,
      favorites: [],
      recents: [],
      recentAt: {},
      loadAgents: async () => {
        const data = await listAgents()
        set({ agents: data.agents })
      },
      setCurrentAgent: (id) => {
        set({ currentAgentId: id })
        get().addRecent(id)
      },
      toggleFavorite: (id) =>
        set((state) => {
          if (state.favorites.includes(id)) {
            return {
              favorites: state.favorites.filter((f) => f !== id),
            }
          }
          let next = [...state.favorites, id]
          if (next.length > MAX_FAVORITES) {
            next = next.slice(next.length - MAX_FAVORITES)
          }
          return { favorites: next }
        }),
      addRecent: (id) =>
        set((state) => {
          const next = [id, ...state.recents.filter((r) => r !== id)]
          return {
            recents: next.slice(0, MAX_RECENTS),
            recentAt: { ...state.recentAt, [id]: Date.now() },
          }
        }),
      moveFavorite: (id, direction) =>
        set((state) => {
          const idx = state.favorites.indexOf(id)
          if (idx < 0) return {}
          const ni = idx + direction
          if (ni < 0 || ni >= state.favorites.length) return {}
          const f = [...state.favorites]
          const t = f[idx]
          f[idx] = f[ni]
          f[ni] = t
          return { favorites: f }
        }),
      setFavoriteOrder: (ids) =>
        set(() => ({
          favorites: ids.filter(Boolean).slice(0, MAX_FAVORITES),
        })),
    }),
    {
      name: LOCAL_STORAGE_KEYS.RECENTS,
      partialize: (state) => ({
        favorites: state.favorites,
        recents: state.recents,
        recentAt: state.recentAt,
      }),
    },
  ),
)
