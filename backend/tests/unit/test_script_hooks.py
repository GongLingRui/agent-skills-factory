"""Tests for script_hooks builder and controlled worker."""

from __future__ import annotations

from agent_factory.core.script_hooks import build_script_hooks
from agent_factory.workers.script_worker import run_controlled_script


def test_build_script_hooks_disabled():
    ent = {"scripts": {"preprocess": [{"id": "x", "entry": "scripts/x.py"}]}}
    assert build_script_hooks(ent, enabled=False) == {}


def test_build_script_hooks_enabled():
    ent = {
        "scripts": {
            "preprocess": [
                {
                    "id": "norm",
                    "entry": "scripts/norm.py",
                    "mode": "controlled_worker",
                }
            ]
        }
    }
    hooks = build_script_hooks(ent, enabled=True)
    assert "preprocess" in hooks
    assert hooks["preprocess"][0]["id"] == "norm"


def test_run_controlled_script_roundtrip():
    source = (
        "output = {'user_message': input.get('user_message', '') + ' [ok]'}"
    )
    out = run_controlled_script(
        script_source=source,
        hook_id="norm",
        input_payload={"user_message": "hi"},
        timeout_seconds=5,
    )
    assert out["user_message"] == "hi [ok]"
