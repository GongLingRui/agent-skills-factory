"""MiniMax chat: tool calls embedded as XML inside text deltas (not OpenAI tool_calls)."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

# Avoid yielding a prefix of ``<minimax:tool_call>`` split across SSE chunks.
_HOLDBACK = 96
_OPEN = "<minimax:tool_call>"
_CLOSE = "</minimax:tool_call>"

_RE_THINKING = re.compile(
    r"<think>.*?</think>\s*",
    re.DOTALL | re.IGNORECASE,
)
_RE_BLOCK = re.compile(
    r"<minimax:tool_call>\s*<invoke\s+name=\"([^\"]+)\"\s*>(.*?)</invoke>\s*</minimax:tool_call>",
    re.DOTALL | re.IGNORECASE,
)
_RE_PARAM = re.compile(
    r"<parameter\s+name=\"([^\"]+)\"\s*>([^<]*)</parameter>",
    re.DOTALL | re.IGNORECASE,
)

# Some models emit pseudo-tool lines instead of OpenAI ``tool_calls`` / MiniMax XML.
_OPEN_BR = "[tool_call]"
_CLOSE_BR = "[/tool_call]"
_RE_BRACKET_BLOCK = re.compile(
    r"\[TOOL_CALL\]\s*(.*?)\s*\[/TOOL_CALL\]",
    re.IGNORECASE | re.DOTALL,
)
_RE_BR_TOOL = re.compile(
    r"""\btool\s*=>\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_RE_BR_FILE_ID = re.compile(
    r"""--\s*file_id\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_RE_BR_FILE_ID_ALT = re.compile(
    r"""\bfile_id\s*=>\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_RE_BR_FILE_ID_JSON = re.compile(r'"file_id"\s*:\s*"([^"]*)"', re.IGNORECASE)

# OpenAI-style: ``<tool_call> {"name": "doc.extract", "parameters": {...}} </tool_call>``
_RE_ANGLE_OPEN = re.compile(r"<tool_call\b[^>]*>", re.IGNORECASE)
_RE_ANGLE_CLOSE = re.compile(r"</tool_call\s*>", re.IGNORECASE)


def _tail_might_be_open_prefix(tail: str, tag: str = _OPEN) -> bool:
    """True if ``tail`` is a suffix of some prefix of ``tag`` (case-insensitive)."""
    tl = tail.lower()
    t = tag.lower()
    lim = min(len(tl), len(t))
    for k in range(1, lim + 1):
        if t[:k] == tl[-k:]:
            return True
    return False


def strip_redacted_thinking(text: str) -> str:
    return _RE_THINKING.sub("", text)


def strip_minimax_tool_blocks(text: str) -> str:
    return _RE_BLOCK.sub("", text)


def strip_bracket_tool_blocks(text: str) -> str:
    return _RE_BRACKET_BLOCK.sub("", text)


def strip_angle_json_tool_blocks(text: str) -> str:
    """Remove ``<tool_call> { ... } </tool_call>`` blobs from assistant text."""
    parts: list[str] = []
    pos = 0
    while True:
        m_open = _RE_ANGLE_OPEN.search(text, pos)
        if not m_open:
            parts.append(text[pos:])
            break
        parts.append(text[pos : m_open.start()])
        m_close = _RE_ANGLE_CLOSE.search(text, m_open.end())
        if not m_close:
            parts.append(text[m_open.start() :])
            break
        pos = m_close.end()
    return "".join(parts).strip()


def visible_user_facing_assistant(text: str) -> str:
    """Checkpoint / done payload: no thinking tags, no tool pseudo-markup."""
    t = strip_redacted_thinking(text)
    t = strip_minimax_tool_blocks(t)
    t = strip_angle_json_tool_blocks(t)
    t = strip_bracket_tool_blocks(t)
    return t.strip()


def parse_minimax_tool_calls(text: str) -> list[dict[str, object]]:
    """Build OpenAI-shaped tool_call dicts for ``RunnerService``."""
    out: list[dict[str, object]] = []
    for m in _RE_BLOCK.finditer(text):
        tool_id = m.group(1).strip()
        inner = m.group(2) or ""
        params: dict[str, str] = {}
        for pm in _RE_PARAM.finditer(inner):
            params[pm.group(1).strip()] = (pm.group(2) or "").strip()
        cid = f"mm_{uuid.uuid4().hex[:12]}"
        out.append(
            {
                "id": cid,
                "function": {
                    "name": tool_id,
                    "arguments": json.dumps(params, ensure_ascii=False),
                },
            }
        )
    return out


def parse_bracket_tool_calls(text: str) -> list[dict[str, object]]:
    """Parse ``[TOOL_CALL] ... [/TOOL_CALL]`` (e.g. ``tool => \"doc.extract\"``)."""
    out: list[dict[str, object]] = []
    for m in _RE_BRACKET_BLOCK.finditer(text):
        inner = (m.group(1) or "").strip()
        tm = _RE_BR_TOOL.search(inner)
        tool_id = (tm.group(1).strip() if tm else "").strip()
        if not tool_id:
            continue
        params: dict[str, str] = {}
        for rx in (
            _RE_BR_FILE_ID,
            _RE_BR_FILE_ID_ALT,
            _RE_BR_FILE_ID_JSON,
        ):
            fm = rx.search(inner)
            if fm:
                params["file_id"] = fm.group(1).strip()
                break
        cid = f"br_{uuid.uuid4().hex[:12]}"
        out.append(
            {
                "id": cid,
                "function": {
                    "name": tool_id,
                    "arguments": json.dumps(params, ensure_ascii=False),
                },
            }
        )
    return out


def parse_angle_json_tool_calls(text: str) -> list[dict[str, object]]:
    """Parse ``<tool_call>{"name":"doc.extract","parameters":{...}}</tool_call>``."""
    out: list[dict[str, object]] = []
    pos = 0
    while True:
        m_open = _RE_ANGLE_OPEN.search(text, pos)
        if not m_open:
            break
        m_close = _RE_ANGLE_CLOSE.search(text, m_open.end())
        if not m_close:
            break
        raw = text[m_open.end() : m_close.start()].strip()
        pos = m_close.end()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        raw_name = obj.get("name") or obj.get("tool")
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        tool_id = raw_name.strip()
        params = obj.get("parameters") or obj.get("arguments") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}
        if not isinstance(params, dict):
            params = {}
        cid = f"ag_{uuid.uuid4().hex[:12]}"
        out.append(
            {
                "id": cid,
                "function": {
                    "name": tool_id,
                    "arguments": json.dumps(params, ensure_ascii=False),
                },
            }
        )
    return out


def parse_embedded_tool_calls(text: str) -> list[dict[str, object]]:
    """Prefer MiniMax XML; then angle JSON; otherwise bracket pseudo-calls."""
    mm = parse_minimax_tool_calls(text)
    if mm:
        return mm
    ang = parse_angle_json_tool_calls(text)
    if ang:
        return ang
    return parse_bracket_tool_calls(text)


def _union_tail_might_be_tool_open_prefix(tail: str) -> bool:
    return (
        _tail_might_be_open_prefix(tail, _OPEN)
        or _tail_might_be_open_prefix(tail, _OPEN_BR)
        or _angle_tool_open_prefix_might_match(tail)
    )


def _angle_tool_open_prefix_might_match(tail: str) -> bool:
    """True if ``tail`` may be an incomplete ``<tool_call...>`` opener."""
    return _tail_might_be_open_prefix(tail, "<tool_call>") or _tail_might_be_open_prefix(
        tail, "<tool_call"
    )


@dataclass
class MinimaxStreamYieldController:
    """Hide MiniMax XML, ``<tool_call>`` JSON blobs, and ``[TOOL_CALL]`` from SSE."""

    committed: int = 0
    skip: str = "none"  # none | mm | br | ang

    def on_delta(self, assistant_text: str) -> str:
        """Return safe substring to emit for this ``assistant_text`` snapshot."""
        low = assistant_text.lower()
        out: list[str] = []
        while True:
            if self.skip == "none":
                i_mm = low.find(_OPEN.lower(), self.committed)
                i_br = low.find(_OPEN_BR, self.committed)
                m_ang = _RE_ANGLE_OPEN.search(assistant_text, self.committed)
                i_ang = m_ang.start() if m_ang else -1
                next_i: int | None = None
                next_kind: str | None = None
                for i, kind in ((i_mm, "mm"), (i_br, "br"), (i_ang, "ang")):
                    if i == -1:
                        continue
                    if next_i is None or i < next_i:
                        next_i, next_kind = i, kind
                if next_i is None:
                    tail = assistant_text[self.committed :]
                    if not tail:
                        return "".join(out)
                    if _union_tail_might_be_tool_open_prefix(tail):
                        safe_end = len(assistant_text) - _HOLDBACK
                        if safe_end > self.committed:
                            out.append(
                                assistant_text[self.committed : safe_end]
                            )
                            self.committed = safe_end
                        return "".join(out)
                    out.append(tail)
                    self.committed = len(assistant_text)
                    return "".join(out)
                if next_i > self.committed:
                    out.append(assistant_text[self.committed : next_i])
                    self.committed = next_i
                self.skip = next_kind or "none"
                continue
            if self.skip == "mm":
                close_s = _CLOSE.lower()
                c = low.find(close_s, self.committed)
                if c == -1:
                    return "".join(out)
                end = c + len(_CLOSE)
                self.committed = end
                self.skip = "none"
                continue
            if self.skip == "ang":
                m_close = _RE_ANGLE_CLOSE.search(assistant_text, self.committed)
                if not m_close:
                    return "".join(out)
                self.committed = m_close.end()
                self.skip = "none"
                continue
            close_b = _CLOSE_BR
            c = low.find(close_b, self.committed)
            if c == -1:
                return "".join(out)
            end = c + len(_CLOSE_BR)
            self.committed = end
            self.skip = "none"
            continue

    def flush_end(self, assistant_text: str) -> str:
        """Emit any tail after the model stream ends."""
        low = assistant_text.lower()
        if self.skip == "mm":
            c = low.find(_CLOSE.lower(), self.committed)
            if c != -1:
                end = c + len(_CLOSE)
                self.committed = end
                self.skip = "none"
            else:
                self.committed = len(assistant_text)
                return ""
        elif self.skip == "br":
            c = low.find(_CLOSE_BR, self.committed)
            if c != -1:
                end = c + len(_CLOSE_BR)
                self.committed = end
                self.skip = "none"
            else:
                self.committed = len(assistant_text)
                return ""
        elif self.skip == "ang":
            m_close = _RE_ANGLE_CLOSE.search(assistant_text, self.committed)
            if m_close:
                self.committed = m_close.end()
                self.skip = "none"
            else:
                self.committed = len(assistant_text)
                return ""
        tail = assistant_text[self.committed :]
        if tail:
            self.committed = len(assistant_text)
            return tail
        return ""
