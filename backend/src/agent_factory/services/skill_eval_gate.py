"""Skill Registry eval gate: schema + optional live model scoring (docs/04, docs/27)."""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_factory.config import Settings, get_settings
from agent_factory.core.eval_jsonl import validate_eval_case_dict
from agent_factory.core.eval_scoring import score_case_output
from agent_factory.infra.redis import get_redis
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.eval_chat import collect_chat_text_stream
from agent_factory.services.model_gateway import ModelGateway

logger = logging.getLogger(__name__)


def extract_eval_cases(
    package_metadata: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return inline eval cases from ``package_metadata``.

    Supported keys (first match wins): ``eval_cases``, ``evals_inline``.
    """
    if not package_metadata:
        return []
    for key in ("eval_cases", "evals_inline"):
        raw = package_metadata.get(key)
        if raw is None:
            continue
        if not isinstance(raw, list):
            raise AgentFactoryException(
                "INVALID_EVAL_CASES",
                f"package_metadata.{key} must be a JSON array",
                status_code=400,
            )
        out: list[dict[str, Any]] = []
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                raise AgentFactoryException(
                    "INVALID_EVAL_CASES",
                    f"package_metadata.{key}[{i}] must be an object",
                    status_code=400,
                )
            out.append(item)
        return out
    return []


def validate_eval_cases_schema(cases: list[dict[str, Any]]) -> None:
    """Raise ``EVAL_CASES_INVALID`` if any line fails docs/04 schema."""
    errors: list[str] = []
    for i, case in enumerate(cases):
        for err in validate_eval_case_dict(case):
            errors.append(f"case[{i}] ({case.get('id', '?')}): {err}")
    if errors:
        msg = "; ".join(errors[:25])
        if len(errors) > 25:
            msg += "; ..."
        raise AgentFactoryException(
            "EVAL_CASES_INVALID",
            msg,
            status_code=400,
        )


def _gate_model_name(settings: Settings, gateway: ModelGateway) -> str:
    name = (settings.SKILL_EVAL_GATE_MODEL or "").strip()
    if name:
        return name
    return gateway.default_chat_model()


def effective_eval_gate_rpm(
    settings: Settings,
    gateway: ModelGateway,
    model: str,
) -> int:
    """RPM budget for live eval calls (override vs ``models.yaml``)."""
    if settings.SKILL_EVAL_GATE_RPM > 0:
        return int(settings.SKILL_EVAL_GATE_RPM)
    return gateway.rpm_for(model)


def _rpm_redis_key(logical_model: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in logical_model)
    window = int(time.time()) // 60
    return f"rl:eval_gate:{safe}:{window}"


async def enforce_eval_gate_rpm_slot(*, logical_model: str, rpm_limit: int) -> None:
    """Redis fixed-window limit for eval-gate HTTP calls (cf. IP RL middleware)."""
    if rpm_limit <= 0:
        return
    try:
        redis = get_redis()
        key = _rpm_redis_key(logical_model)
        n = await redis.incr(key)
        if n == 1:
            await redis.expire(key, 70)
        if n > rpm_limit:
            raise AgentFactoryException(
                "EVAL_GATE_RATE_LIMITED",
                "Skill eval gate model RPM exceeded; retry later",
                status_code=429,
            )
    except AgentFactoryException:
        raise
    except Exception:
        logger.warning(
            "eval gate RPM check skipped (Redis unavailable)",
            exc_info=True,
        )


async def run_skill_registry_eval_gate(
    *,
    package_metadata: dict[str, Any] | None,
    settings: Settings | None = None,
) -> None:
    """Reject registration when eval cases are invalid or live scoring fails.

    - When ``SKILL_EVAL_CASES_REQUIRED`` is true (prd §8.5), at least one eval
      line must be present in ``eval_cases`` or ``evals_inline``.
    - Always validates schema when ``eval_cases`` / ``evals_inline`` is non-empty.
    - Live model calls run only if ``SKILL_EVAL_GATE_LIVE`` is true (ops toggle).
    """
    cfg = settings or get_settings()
    cases = extract_eval_cases(package_metadata)
    if not cases:
        if cfg.SKILL_EVAL_CASES_REQUIRED:
            raise AgentFactoryException(
                "EVAL_CASES_REQUIRED",
                (
                    "package_metadata must include at least one eval case "
                    "(eval_cases or evals_inline); see docs/04, prd §8.5."
                ),
                status_code=400,
            )
        return

    validate_eval_cases_schema(cases)

    if not cfg.SKILL_EVAL_GATE_LIVE:
        return

    gateway = ModelGateway(cfg)
    model = _gate_model_name(cfg, gateway)
    rpm_cap = effective_eval_gate_rpm(cfg, gateway, model)
    try:
        for case in cases:
            cid = case.get("id", "?")
            inp = case.get("input") or {}
            msg = inp.get("message") if isinstance(inp, dict) else None
            if not isinstance(msg, str) or not msg.strip():
                raise AgentFactoryException(
                    "EVAL_CASES_INVALID",
                    f"case {cid}: input.message required for live gate",
                    status_code=400,
                )
            await enforce_eval_gate_rpm_slot(logical_model=model, rpm_limit=rpm_cap)
            text_out = await collect_chat_text_stream(
                gateway,
                model=model,
                user_message=msg,
            )
            score, reasons = score_case_output(text=text_out, case=case)
            min_s = float(case.get("min_score", 0.0))
            if score < min_s:
                detail = f"case {cid}: score={score:.3f} < min_score={min_s:.3f}"
                if reasons:
                    detail += "; " + "; ".join(reasons)
                raise AgentFactoryException(
                    "EVAL_GATE_FAILED",
                    detail,
                    status_code=422,
                )
    finally:
        await gateway.close()
