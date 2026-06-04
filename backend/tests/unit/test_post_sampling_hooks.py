"""Tests for post_sampling_hooks chain."""

from __future__ import annotations

from agent_factory.core.post_sampling_hooks import (
    POST_SAMPLING_HOOKS,
    apply_post_sampling_hooks,
    normalize_whitespace,
    redact_sensitive_snippets_hook,
    strip_trailing_incomplete_sentences,
    visible_user_facing_assistant_hook,
)
from agent_factory.db.models.run_spec import RunSpec


def test_hooks_registered():
    assert len(POST_SAMPLING_HOOKS) >= 4


def test_redact_sensitive_snippets():
    text = "My key is sk-12345678901234567890 and done."
    out = redact_sensitive_snippets_hook(text, RunSpec(run_id="r1"))
    assert "sk-12345678901234567890" not in out
    assert "[REDACTED_SECRET]" in out


def test_visible_user_facing_assistant():
    text = "Hello \u003cthink\u003ethinking...\u003c/think\u003e world"
    out = visible_user_facing_assistant_hook(text, RunSpec(run_id="r1"))
    assert "think" not in out
    assert "world" in out


def test_strip_trailing_incomplete_sentences():
    text = "Hello world. This is a sentence. Some trailing text without end"
    out = strip_trailing_incomplete_sentences(text, RunSpec(run_id="r1"))
    assert out.endswith(".")
    assert "trailing text" not in out


def test_strip_trailing_incomplete_sentences_short_tail():
    text = "Hello world. This is fine."
    out = strip_trailing_incomplete_sentences(text, RunSpec(run_id="r1"))
    assert out == text


def test_normalize_whitespace():
    text = "Hello\n\n\n\n\nWorld"
    out = normalize_whitespace(text, RunSpec(run_id="r1"))
    assert "\n\n\n" not in out
    assert "\n\n" in out


def test_apply_post_sampling_hooks_chain():
    text = "Hello world.\n\n\n\n\n"
    out = apply_post_sampling_hooks(text, RunSpec(run_id="r1"))
    assert "\n\n\n" not in out
