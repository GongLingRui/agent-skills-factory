"""ORM: roles, permissions, role_permissions, user_roles."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class Role(Base):
    """RBAC role."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)


class Permission(Base):
    """RBAC permission."""

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    resource: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(16))


class RolePermission(Base):
    """Role-permission association."""

    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    """User-role assignment (per department)."""

    __tablename__ = "user_roles"

    user_id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    role_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    department: Mapped[str] = mapped_column(String(64), primary_key=True)
    granted_by: Mapped[str | None] = mapped_column(String(64))
    granted_at: Mapped[datetime | None] = mapped_column(DateTime)
