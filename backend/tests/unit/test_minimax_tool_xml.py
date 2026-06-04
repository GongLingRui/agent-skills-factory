"""MiniMax inline tool XML parsing."""

from agent_factory.core.minimax_tool_xml import (
    MinimaxStreamYieldController,
    parse_angle_json_tool_calls,
    parse_bracket_tool_calls,
    parse_embedded_tool_calls,
    parse_minimax_tool_calls,
    visible_user_facing_assistant,
)


def test_parse_doc_extract_sample() -> None:
    raw = (
        "好的。\n<minimax:tool_call>\n<invoke name=\"doc.extract\">\n"
        '<parameter name="file_id">file_bdd8f291dfeb4efeb67db2cbded62d68'
        "</parameter>\n</invoke>\n</minimax:tool_call>"
    )
    calls = parse_minimax_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "doc.extract"
    assert "file_bdd8f291" in str(calls[0]["function"]["arguments"])


def test_visible_strips_block_and_thinking() -> None:
    raw = (
        "<think>x</think>\n可见\n"
        "<minimax:tool_call><invoke name=\"doc.extract\">"
        '<parameter name="file_id">f1</parameter></invoke></minimax:tool_call>'
    )
    v = visible_user_facing_assistant(raw)
    assert "minimax" not in v.lower()
    assert "redacted" not in v.lower()
    assert "可见" in v


def test_parse_bracket_doc_extract_ruby_style() -> None:
    raw = (
        '[TOOL_CALL] {tool => "doc.extract", args => { --file_id '
        '"file_43c553eb4edc405badb1825b7994382e" }} [/TOOL_CALL]'
    )
    calls = parse_bracket_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "doc.extract"
    assert "file_43c553eb4edc405badb1825b7994382e" in str(
        calls[0]["function"]["arguments"]
    )


def test_parse_angle_json_doc_extract() -> None:
    raw = (
        '<tool_call> {"name": "doc.extract", "parameters": '
        '{"file_id": "file_bdce72db1eb14762a503c69f2d0a6793"}} </tool_call>'
    )
    calls = parse_angle_json_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "doc.extract"
    assert "file_bdce72db1eb14762a503c69f2d0a6793" in str(
        calls[0]["function"]["arguments"]
    )


def test_visible_strips_angle_json_tool_call() -> None:
    raw = (
        "前文\n<tool_call> "
        '{"name": "doc.extract", "parameters": {"file_id": "f1"}}'
        " </tool_call>\n后文"
    )
    v = visible_user_facing_assistant(raw)
    assert "tool_call" not in v.lower()
    assert "doc.extract" not in v
    assert "前文" in v
    assert "后文" in v


def test_stream_controller_hides_angle_json_tool() -> None:
    ctl = MinimaxStreamYieldController()
    full = ""
    chunks: list[str] = []
    for part in (
        "请稍等\n<tool_call>",
        ' {"name": "doc.extract", "parameters": {"file_id": "x"}}',
        " </tool_call>\n完成",
    ):
        full += part
        chunks.append(ctl.on_delta(full))
    chunks.append(ctl.flush_end(full))
    joined = "".join(x for x in chunks if x)
    assert "tool_call" not in joined.lower()
    assert "doc.extract" not in joined
    assert "请稍等" in joined
    assert "完成" in joined


def test_parse_embedded_prefers_minimax_xml() -> None:
    raw = (
        '<minimax:tool_call><invoke name="kb.search">'
        '<parameter name="query">x</parameter></invoke></minimax:tool_call>'
    )
    calls = parse_embedded_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "kb.search"


def test_visible_strips_bracket_blocks() -> None:
    raw = '说明 [TOOL_CALL] {tool => "doc.extract"} [/TOOL_CALL] 结束'
    v = visible_user_facing_assistant(raw)
    assert "tool_call" not in v.lower()
    assert "说明" in v
    assert "结束" in v


def test_stream_controller_hides_bracket_tool() -> None:
    ctl = MinimaxStreamYieldController()
    full = ""
    chunks: list[str] = []
    for part in (
        "请看",
        "[TOOL_CALL]",
        ' {tool => "doc.extract"',
        ", args => {}} [/TOOL_CALL]",
    ):
        full += part
        chunks.append(ctl.on_delta(full))
    tail = ctl.flush_end(full)
    chunks.append(tail)
    joined = "".join(x for x in chunks if x)
    assert "tool_call" not in joined.lower()
    assert "doc.extract" not in joined
    assert "请看" in joined


def test_stream_controller_hides_tool_xml() -> None:
    ctl = MinimaxStreamYieldController()
    full = ""
    out = []
    for part in ("前文", "<minimax:tool_call>", "\n<invoke ", 'name="doc.extract">'):
        full += part
        out.append(ctl.on_delta(full))
    assert "前文" in "".join(out)
    full += (
        '\n<parameter name="file_id">fid</parameter>\n</invoke>\n</minimax:tool_call>'
    )
    out.append(ctl.on_delta(full))
    tail = ctl.flush_end(full)
    out.append(tail)
    joined = "".join(x for x in out if x)
    assert "minimax" not in joined.lower()
    assert "invoke" not in joined.lower()
