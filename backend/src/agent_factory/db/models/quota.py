"""ORM: token_quotas and token_quota_history."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class TokenQuota(Base):
    """Token budget quota per scope."""

    __tablename__ = "token_quotas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scope: Mapped[str] = mapped_column(String(16))
    scope_id: Mapped[str] = mapped_column(String(64))
    budget_tokens: Mapped[int] = mapped_column(BigInteger)
    used_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)


class TokenQuotaHistory(Base):
    """Token quota change history."""

    __tablename__ = "token_quota_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scope: Mapped[str] = mapped_column(String(16))
    scope_id: Mapped[str] = mapped_column(String(64))
    previous_budget: Mapped[int | None] = mapped_column(BigInteger)
    new_budget: Mapped[int] = mapped_column(BigInteger)
    change_reason: Mapped[str | None] = mapped_column(String)
    effective_period: Mapped[str] = mapped_column(String(7))
    effective_immediately: Mapped[bool] = mapped_column(default=True)
    operator_id: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
