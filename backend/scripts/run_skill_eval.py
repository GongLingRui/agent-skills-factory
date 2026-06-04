#!/usr/bin/env python3
"""Run Skill eval JSONL against the model gateway (docs/04, docs/27).

Uses existing :class:`ModelGateway` streaming aggregation — no duplicate HTTP client.

Examples::

    # Format-only (no network)
    uv run python scripts/run_skill_eval.py --cases /path/to/skill_cases.jsonl \\
        --dry-run

    # Live scoring (requires models.yaml endpoints reachable)
    uv run python scripts/run_skill_eval.py --cases evals/skill_cases.jsonl \\
        --model qwen3-32b
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_factory.config import get_settings
from agent_factory.core.eval_jsonl import validate_eval_case_dict
from agent_factory.core.eval_scoring import score_case_output
from agent_factory.services.eval_chat import collect_chat_text_stream
from agent_factory.services.model_gateway import ModelGateway

logger = logging.getLogger("run_skill_eval")


def _load_cases(path: Path) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    cases: list[dict] = []
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{line_no}: invalid JSON: {exc}")
            continue
        if not isinstance(obj, dict):
            errors.append(f"{path}:{line_no}: case must be an object")
            continue
        for err in validate_eval_case_dict(obj):
            errors.append(f"{path}:{line_no}: {err}")
        cases.append(obj)
    return cases, errors


async def _run_async(args: argparse.Namespace) -> int:
    path = Path(args.cases)
    if not path.is_file():
        print(f"ERROR: not a file: {path}", file=sys.stderr)
        return 2

    cases, errors = _load_cases(path)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    if not cases:
        print(f"ERROR: no JSON cases in {path}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Dry-run OK: {len(cases)} case(s) in {path}")
        return 0

    settings = get_settings()
    gateway = ModelGateway(settings)
    try:
        failed: list[str] = []
        for case in cases:
            cid = case.get("id", "?")
            inp = case.get("input") or {}
            msg = inp.get("message") if isinstance(inp, dict) else None
            if not isinstance(msg, str):
                print(f"case {cid}: skip (no input.message)", file=sys.stderr)
                failed.append(str(cid))
                continue
            text_out = await collect_chat_text_stream(
                gateway,
                model=args.model,
                user_message=msg,
            )
            score, reasons = score_case_output(text=text_out, case=case)
            min_s = float(case.get("min_score", 0.0))
            ok = score >= min_s
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {cid} score={score:.3f} min={min_s:.3f}")
            if reasons:
                for r in reasons:
                    print(f"         {r}")
            if not ok:
                failed.append(str(cid))
                if args.verbose:
                    print(f"         output (trunc): {text_out[:500]!r}")

        if failed:
            print(f"Failed cases: {', '.join(failed)}", file=sys.stderr)
            return 1
        return 0
    finally:
        await gateway.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run skill_cases.jsonl against ModelGateway",
    )
    parser.add_argument(
        "--cases",
        required=True,
        help="Path to skill_cases.jsonl",
    )
    parser.add_argument(
        "--model",
        default="qwen3-32b",
        help="Logical model name from models.yaml (default: qwen3-32b)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate JSONL only; do not call the model",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="On failure, print truncated model output",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    return asyncio.run(_run_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
