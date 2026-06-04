/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  /** When 'true', call POST /auth/dev/session if no portal token (local only). */
  readonly VITE_DEV_WIDGET_AUTH_BYPASS?: string
  /** Default agent_id for dev session bootstrap (must exist in registry). */
  readonly VITE_DEV_DEFAULT_AGENT_ID?: string
  /** Optional build / version string for widget header (e.g. git short SHA). */
  readonly VITE_WIDGET_BUILD_LABEL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
