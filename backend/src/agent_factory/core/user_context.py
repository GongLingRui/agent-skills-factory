"""Authenticated user context (from session cookie)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class UserContext:
    """Resolved from HttpOnly session cookie + Redis/DB."""

    session_id: str
    user_id_hash: str
    department: str | None
    permissions: tuple[str, ...]
    allowed_agents: tuple[str, ...] | None = None
    # Portal ``data_domains`` claim; ``None`` = omit user slice (docs/07).
    data_domains: tuple[str, ...] | None = None
