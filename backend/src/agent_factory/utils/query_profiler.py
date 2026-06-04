"""Query profiling: per-turn phase timing and slow-operation warnings."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_WARN_MS = 100.0
_WARN_MS_SLOW = 1000.0


@dataclass
class QueryProfiler:
    """Context manager style profiler for a single turn.

    Usage::

        profiler = QueryProfiler()
        profiler.checkpoint("load_history")
        ...
        profiler.checkpoint("model_call_start")
        ...
        profiler.checkpoint("first_chunk_received")
        ...
        profiler.finish()
    """

    run_id: str = ""
    session_id: str = ""
    turn_number: int = 0
    _phases: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _t0: float = field(default_factory=time.perf_counter, repr=False)
    _last: float = field(default_factory=time.perf_counter, repr=False)

    def checkpoint(self, phase: str) -> None:
        now = time.perf_counter()
        elapsed_ms = (now - self._last) * 1000.0
        total_ms = (now - self._t0) * 1000.0
        self._phases.append(
            {
                "phase": phase,
                "elapsed_ms": round(elapsed_ms, 2),
                "total_ms": round(total_ms, 2),
            }
        )
        self._last = now
        if elapsed_ms > _WARN_MS_SLOW:
            logger.warning(
                "query_profiler_slow_phase",
                extra={
                    "run_id": self.run_id,
                    "session_id": self.session_id,
                    "turn_number": self.turn_number,
                    "phase": phase,
                    "elapsed_ms": round(elapsed_ms, 2),
                },
            )
        elif elapsed_ms > _WARN_MS:
            logger.info(
                "query_profiler_phase",
                extra={
                    "run_id": self.run_id,
                    "session_id": self.session_id,
                    "turn_number": self.turn_number,
                    "phase": phase,
                    "elapsed_ms": round(elapsed_ms, 2),
                },
            )

    def finish(self) -> dict[str, Any]:
        now = time.perf_counter()
        total_ms = (now - self._t0) * 1000.0
        summary = {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "turn_number": self.turn_number,
            "total_ms": round(total_ms, 2),
            "phases": self._phases,
        }
        if total_ms > _WARN_MS_SLOW:
            logger.warning(
                "query_profiler_slow_turn",
                extra={
                    "run_id": self.run_id,
                    "session_id": self.session_id,
                    "turn_number": self.turn_number,
                    "total_ms": round(total_ms, 2),
                },
            )
        return summary
