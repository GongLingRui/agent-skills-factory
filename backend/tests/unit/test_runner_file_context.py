"""Runner user-message augmentation for widget file_ids."""

from agent_factory.services.runner_service import _user_message_for_model_with_files


def test_no_files_returns_plain() -> None:
    assert _user_message_for_model_with_files("hi", None) == "hi"
    assert _user_message_for_model_with_files("hi", []) == "hi"


def test_hint_only_when_no_preload() -> None:
    out = _user_message_for_model_with_files("总结", ["file_abc"])
    assert "总结" in out
    assert "file_abc" in out
    assert "doc.extract" in out


def test_preload_appended() -> None:
    out = _user_message_for_model_with_files(
        "总结",
        ["file_abc"],
        preloaded="\n\n--- excerpt ---\nhello",
    )
    assert "总结" in out
    assert "excerpt" in out
    assert "file_abc" in out
