"""RBAC permission codes, role expansion, effective sets (docs/12, docs/51)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Literal

from agent_factory.core.user_context import UserContext
from agent_factory.middleware.error_handler import AgentFactoryException

PERM_AGENT_READ = "agent.read"
PERM_AGENT_WRITE = "agent.write"
PERM_AGENT_ADMIN = "agent.admin"
PERM_SKILL_PUBLISH = "skill.publish"
PERM_SKILL_READ = "skill.read"
PERM_TOOL_ADMIN = "tool.admin"
PERM_AUDIT_READ = "audit.read"
PERM_DEGRADATION_CONTROL = "degradation.control"
PERM_POLICY_ADMIN = "policy.admin"

ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_DEPARTMENT_ADMIN = "department_admin"
ROLE_AUDITOR = "auditor"

_PLATFORM_EXPANSION: frozenset[str] = frozenset(
    {
        PERM_AGENT_READ,
        PERM_AGENT_WRITE,
        PERM_AGENT_ADMIN,
        PERM_SKILL_PUBLISH,
        PERM_TOOL_ADMIN,
        PERM_AUDIT_READ,
        PERM_DEGRADATION_CONTROL,
        PERM_POLICY_ADMIN,
    }
)

_DEPARTMENT_EXPANSION: frozenset[str] = frozenset(
    {
        PERM_AGENT_READ,
        PERM_AGENT_WRITE,
        PERM_AGENT_ADMIN,
        PERM_SKILL_READ,
        PERM_POLICY_ADMIN,
    }
)

_AUDITOR_EXPANSION: frozenset[str] = frozenset(
    {
        PERM_AUDIT_READ,
        PERM_AGENT_READ,
    }
)

_LEGACY_AGENT_ADMIN_EXTRA: frozenset[str] = frozenset(
    {
        PERM_SKILL_PUBLISH,
        PERM_TOOL_ADMIN,
        PERM_AUDIT_READ,
        PERM_DEGRADATION_CONTROL,
        PERM_POLICY_ADMIN,
    }
)


def effective_permissions(
    permissions: tuple[str, ...],
    *,
    legacy_agent_admin_implies_full: bool = True,
) -> frozenset[str]:
    """Expand role tokens and optional legacy ``agent.admin`` aliases."""
    base: set[str] = set(permissions)
    if ROLE_PLATFORM_ADMIN in base:
        base |= set(_PLATFORM_EXPANSION)
    if ROLE_DEPARTMENT_ADMIN in base:
        base |= set(_DEPARTMENT_EXPANSION)
    if ROLE_AUDITOR in base:
        base |= set(_AUDITOR_EXPANSION)
    if legacy_agent_admin_implies_full and PERM_AGENT_ADMIN in base:
        base |= set(_LEGACY_AGENT_ADMIN_EXTRA)
    return frozenset(base)


def has_any_permission(eff: frozenset[str], *need: str) -> bool:
    return any(n in eff for n in need)


def can_view_product_metrics(
    eff: frozenset[str],
    raw_permissions: tuple[str, ...],
) -> bool:
    """Who may call ``GET /admin/product-metrics/summary`` (docs/33)."""
    if ROLE_PLATFORM_ADMIN in raw_permissions or ROLE_DEPARTMENT_ADMIN in raw_permissions:
        return True
    return has_any_permission(
        eff,
        PERM_AGENT_ADMIN,
        PERM_AGENT_WRITE,
        PERM_AUDIT_READ,
    )


@dataclass(frozen=True)
class RegistryDeptScope:
    """Agent 注册中心部门范围（docs/51 阶段 C）。"""

    mode: Literal["global", "owner_eq", "blocked"]
    owner_value: str | None = None


def registry_department_scope_for_user(user: UserContext | None) -> RegistryDeptScope:
    """Bearer / ``platform_admin`` / 非部门管理员 → 不按 owner 过滤。"""
    if user is None:
        return RegistryDeptScope("global")
    raw = set(user.permissions)
    if ROLE_PLATFORM_ADMIN in raw:
        return RegistryDeptScope("global")
    if ROLE_DEPARTMENT_ADMIN in raw:
        dept = (user.department or "").strip()
        if not dept:
            return RegistryDeptScope("blocked")
        return RegistryDeptScope("owner_eq", dept)
    return RegistryDeptScope("global")


def assert_registry_department_allowed(scope: RegistryDeptScope) -> None:
    """部门管理员缺少 department 时禁止一切注册中心写操作。"""
    if scope.mode == "blocked":
        raise AgentFactoryException(
            "FORBIDDEN",
            "department_admin 需要门户 JWT 的 department claim",
            status_code=403,
        )
