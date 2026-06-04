export interface AgentUIConfig {
  title?: string
  avatar?: string
  welcome_message?: string
  input_placeholder?: string
  quick_actions?: Array<{ label: string; prompt: string }>
  attachments?: {
    enabled?: boolean
    accept?: string[]
    max_size_mb?: number
  }
  /** When true, ```html fences render as live preview (slides / single-file HTML agents). */
  render_html_preview?: boolean
}

export interface AgentInfo {
  id: string
  name: string
  description: string
  ui_config: AgentUIConfig
}
