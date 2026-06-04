"""Post-sampling hooks: applied to assistant text before yielding to user."""

from __future__ import annotations

import re
from typing import Any, Callable

from agent_factory.db.models.run_spec import RunSpec

POST_SAMPLING_HOOKS: list[Callable[[str, RunSpec], str]] = []


def register_post_sampling_hook(
    fn: Callable[[str, RunSpec], str],
) -> Callable[[str, RunSpec], str]:
    POST_SAMPLING_HOOKS.append(fn)
    return fn


def apply_post_sampling_hooks(text: str, run_spec: RunSpec) -> str:
    for hook in POST_SAMPLING_HOOKS:
        text = hook(text, run_spec)
    return text


@register_post_sampling_hook
def redact_sensitive_snippets_hook(text: str, _run_spec: RunSpec) -> str:
    from agent_factory.core.output_redaction import redact_sensitive_snippets

    return redact_sensitive_snippets(text)


@register_post_sampling_hook
def visible_user_facing_assistant_hook(text: str, _run_spec: RunSpec) -> str:
    from agent_factory.core.minimax_tool_xml import visible_user_facing_assistant

    return visible_user_facing_assistant(text)


@register_post_sampling_hook
def strip_trailing_incomplete_sentences(text: str, _run_spec: RunSpec) -> str:
    """Remove trailing incomplete sentence if output was likely truncated."""
    if not text:
        return text
    # Find the last sentence-ending punctuation
    last_end = max(text.rfind("。"), text.rfind("."), text.rfind("?"), text.rfind("？"), text.rfind("!"), text.rfind("！"))
    if last_end <= 0:
        return text
    # If there's substantial trailing content after last sentence end (more than 30 chars),
    # and no newline, consider it incomplete
    tail = text[last_end + 1 :]
    if len(tail) > 30 and "\n" not in tail:
        return text[: last_end + 1]
    return text


@register_post_sampling_hook
def normalize_whitespace(text: str, _run_spec: RunSpec) -> str:
    """Collapse three+ consecutive newlines to two; trim trailing whitespace."""
    if not text:
        return text
    text = text.rstrip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text
