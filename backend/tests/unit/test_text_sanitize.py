"""Unicode / invisible char stripping for chat input."""

from agent_factory.core.text_sanitize import strip_format_and_control_chars


def test_strips_zero_width_and_controls():
    raw = "hello\u200b\u200c\u200d\u2060world"
    out = strip_format_and_control_chars(raw, max_chars=1000)
    assert out == "helloworld"


def test_strips_bidi_overrides():
    raw = "a\u202eb\u202c"
    out = strip_format_and_control_chars(raw, max_chars=1000)
    assert "b" in out


def test_respects_max_chars():
    raw = "x" * 100
    out = strip_format_and_control_chars(raw, max_chars=10)
    assert len(out) == 10
