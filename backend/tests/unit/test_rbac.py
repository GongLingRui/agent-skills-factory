"""RBAC role expansion and helpers (docs/51)."""

from agent_factory.core.rbac import (
    PERM_AGENT_ADMIN,
    PERM_AGENT_WRITE,
    PERM_AUDIT_READ,
    PERM_SKILL_PUBLISH,
    ROLE_DEPARTMENT_ADMIN,
    ROLE_PLATFORM_ADMIN,
    can_view_product_metrics,
    effective_permissions,
    has_any_permission,
    registry_department_scope_for_user,
)
from agent_factory.core.user_context import UserContext


def test_platform_admin_expands() -> None:
    eff = effective_permissions(("platform_admin",), legacy_agent_admin_implies_full=True)
    assert PERM_SKILL_PUBLISH in eff
    assert PERM_AUDIT_READ in eff


def test_legacy_agent_admin_implies_extra_when_enabled() -> None:
    eff = effective_permissions((PERM_AGENT_ADMIN,), legacy_agent_admin_implies_full=True)
    assert PERM_SKILL_PUBLISH in eff
    assert PERM_AUDIT_READ in eff


def test_legacy_agent_admin_no_extra_when_disabled() -> None:
    eff = effective_permissions((PERM_AGENT_ADMIN,), legacy_agent_admin_implies_full=False)
    assert PERM_AGENT_ADMIN in eff
    assert PERM_SKILL_PUBLISH not in eff


def test_has_any_permission() -> None:
    eff = effective_permissions(("auditor",), legacy_agent_admin_implies_full=True)
    assert has_any_permission(eff, PERM_AUDIT_READ)
    assert not has_any_permission(eff, PERM_SKILL_PUBLISH)


def test_can_view_product_metrics_department_role_raw() -> None:
    raw = ("department_admin",)
    eff = effective_permissions(raw, legacy_agent_admin_implies_full=True)
    assert can_view_product_metrics(eff, raw)


def test_can_view_product_metrics_write_expanded() -> None:
    raw = (PERM_AGENT_WRITE,)
    eff = effective_permissions(raw, legacy_agent_admin_implies_full=True)
    assert can_view_product_metrics(eff, raw)


def test_registry_scope_platform_global() -> None:
    u = UserContext(
        session_id="s",
        user_id_hash="h" * 8,
        department="hq",
        permissions=(ROLE_PLATFORM_ADMIN,),
    )
    sc = registry_department_scope_for_user(u)
    assert sc.mode == "global"


def test_registry_scope_department_owner_eq() -> None:
    u = UserContext(
        session_id="s",
        user_id_hash="h" * 8,
        department="dept-a",
        permissions=(ROLE_DEPARTMENT_ADMIN,),
    )
    sc = registry_department_scope_for_user(u)
    assert sc.mode == "owner_eq"
    assert sc.owner_value == "dept-a"


def test_registry_scope_department_blocked_without_dept() -> None:
    u = UserContext(
        session_id="s",
        user_id_hash="h" * 8,
        department=None,
        permissions=(ROLE_DEPARTMENT_ADMIN,),
    )
    sc = registry_department_scope_for_user(u)
    assert sc.mode == "blocked"


def test_registry_scope_bearer_is_global() -> None:
    assert registry_department_scope_for_user(None).mode == "global"
