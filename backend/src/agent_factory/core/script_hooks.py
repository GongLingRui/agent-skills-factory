"""Build RunSpec ``script_hooks`` from enterprise.yaml (docs/25, P2)."""

from __future__ import annotations

from typing import Any


def build_script_hooks(
    merged_enterprise: dict[str, Any] | None,
    *,
    enabled: bool,
) -> dict[str, Any]:
    """Return preprocess/postprocess hook lists; empty when disabled."""
    if not enabled:
        return {}
    ent = merged_enterprise if isinstance(merged_enterprise, dict) else {}
    scripts = ent.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for phase in ("preprocess", "postprocess"):
        raw = scripts.get(phase)
        if not isinstance(raw, list):
            continue
        hooks: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, str):
                hooks.append(
                    {
                        "id": item.rsplit("/", 1)[-1].replace(".py", ""),
                        "entry": item,
                        "mode": "controlled_worker",
                        "timeout_seconds": 10,
                        "network": False,
                    }
                )
                continue
            if not isinstance(item, dict):
                continue
            mode = str(item.get("mode") or "controlled_worker")
            if mode != "controlled_worker":
                continue
            hid = str(item.get("id") or "").strip()
            entry = str(item.get("entry") or "").strip()
            if not hid or not entry:
                continue
            hooks.append(
                {
                    "id": hid,
                    "entry": entry,
                    "mode": "controlled_worker",
                    "timeout_seconds": int(item.get("timeout_seconds", 10)),
                    "network": bool(item.get("network", False)),
                    "filesystem": str(item.get("filesystem", "temp_only")),
                    "max_memory_mb": int(item.get("max_memory_mb", 512)),
                    "allowed_runtime": str(
                        item.get("allowed_runtime", "python3.11")
                    ),
                }
            )
        if hooks:
            out[phase] = hooks
    return out
