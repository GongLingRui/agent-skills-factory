/** 管理台侧栏：按 docs/33、docs/51 与 ``GET /auth/me`` 能力对齐。 */

export type AdminNavItem = {
  to: string
  label: string
  requires:
    | 'agents'
    | 'audit'
    | 'degradation'
    | 'metrics'
    | 'skills'
    | 'tools'
    | 'session_trace'
    | 'policies'
    | 'quotas'
    | 'users'
}

export const ADMIN_NAV: AdminNavItem[] = [
  { to: '/admin/agents', label: 'Agent 注册', requires: 'agents' },
  { to: '/admin/skills', label: 'Skill 目录', requires: 'skills' },
  { to: '/admin/tools', label: 'Tool 目录', requires: 'tools' },
  { to: '/admin/policies', label: '策略', requires: 'policies' },
  { to: '/admin/quotas', label: 'Token 预算', requires: 'quotas' },
  { to: '/admin/users', label: '用户与部门', requires: 'users' },
  { to: '/admin/audit', label: '审计查询', requires: 'audit' },
  { to: '/admin/session-trace', label: '会话轨迹', requires: 'session_trace' },
  { to: '/admin/degradation', label: '降级控制', requires: 'degradation' },
  { to: '/admin/metrics', label: '产品指标', requires: 'metrics' },
]

export type AdminMeCaps = {
  effective_permissions?: string[]
  permissions?: string[]
  can_view_product_metrics?: boolean
  rbac?: { permission_cache_seconds?: number }
}

function navItemVisible(
  item: AdminNavItem,
  eff: Set<string>,
  caps: AdminMeCaps,
): boolean {
  switch (item.requires) {
    case 'agents':
      return eff.has('agent.write') || eff.has('agent.admin')
    case 'skills':
      return (
        eff.has('skill.read') ||
        eff.has('skill.publish') ||
        eff.has('agent.admin')
      )
    case 'tools':
      return (
        eff.has('agent.read') ||
        eff.has('tool.admin') ||
        eff.has('agent.admin')
      )
    case 'audit':
      return eff.has('audit.read')
    case 'session_trace':
      return eff.has('audit.read')
    case 'degradation':
      return eff.has('degradation.control')
    case 'metrics':
      return caps.can_view_product_metrics === true
    case 'policies':
      return (
        eff.has('policy.admin') ||
        Boolean(caps.permissions?.includes('platform_admin'))
      )
    case 'quotas':
      return (
        Boolean(caps.permissions?.includes('platform_admin')) ||
        Boolean(caps.permissions?.includes('department_admin'))
      )
    case 'users':
      return Boolean(caps.permissions?.includes('platform_admin'))
    default:
      return false
  }
}

/** ``hasBearer`` 时保留运维全菜单；否则按 ``effective_permissions`` 过滤。 */
export function filterAdminNav(
  caps: AdminMeCaps | null,
  hasBearer: boolean,
): AdminNavItem[] {
  if (hasBearer) {
    return [...ADMIN_NAV]
  }
  if (!caps?.effective_permissions?.length) {
    return []
  }
  const eff = new Set(caps.effective_permissions)
  return ADMIN_NAV.filter((item) => navItemVisible(item, eff, caps))
}
