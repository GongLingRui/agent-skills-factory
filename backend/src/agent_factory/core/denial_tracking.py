"""Permission-denial circuit breaker for tool calls.

Prevents infinite loops where the model repeatedly asks for a disallowed tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DenialTracker:
    """Track consecutive and total permission denials per session.

    - ``max_consecutive``: after this many denials in a row, auto-block.
    - ``max_total``: after this many denials total, auto-block.
    """

    max_consecutive: int = 3
    max_total: int = 20
    _consecutive: int = field(default=0, repr=False)
    _total: int = field(default=0, repr=False)

    def check_and_record(self, tool_id: str, *, denied: bool) -> bool:
        """Record a permission outcome and return True if the request should
        be allowed to proceed, False if it should be auto-blocked.

        When *denied* is True we increment counters; when False we reset the
        consecutive counter.
        """
        if not denied:
            self._consecutive = 0
            return True

        self._consecutive += 1
        self._total += 1

        if self._consecutive >= self.max_consecutive:
            return False
        if self._total >= self.max_total:
            return False
        return True

    def is_blocked(self) -> bool:
        """True if either threshold has been exceeded."""
        return (
            self._consecutive >= self.max_consecutive
            or self._total >= self.max_total
        )

    def reset(self) -> None:
        self._consecutive = 0
        self._total = 0
