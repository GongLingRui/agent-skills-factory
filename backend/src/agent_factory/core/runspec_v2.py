"""RunSpec schema v2 runtime adjustments (docs/05 §版本化)."""

from __future__ import annotations

from typing import Any


def apply_v2_runtime_overrides(
    runtime: dict[str, Any] | None,
    *,
    runspec_schema_version: int,
) -> dict[str, Any]:
    """v2: stricter defaults layered on v1 ``runtime`` dict."""
    base: dict[str, Any] = dict(runtime or {})
    if runspec_schema_version < 2:
        return base
    ctx = base.get("context_memory")
    if not isinstance(ctx, dict):
        base["context_memory"] = {
            "cross_session_memory_enabled": True,
            "max_summary_chars": 2000,
        }
    else:
        ctx = dict(ctx)
        ctx.setdefault("cross_session_memory_enabled", True)
        ctx.setdefault("max_summary_chars", 2000)
        base["context_memory"] = ctx
    mt = base.get("max_turns")
    if isinstance(mt, int) and mt > 12:
        base["max_turns"] = 12
    base["runspec_v2_semantics"] = True
    return base


def v2_requires_strict_schema_validation(runspec_schema_version: int) -> bool:
    return runspec_schema_version >= 2
