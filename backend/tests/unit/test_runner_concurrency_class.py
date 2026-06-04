"""Runner → model queue concurrency_class mapping (docs/10)."""

from types import SimpleNamespace

from agent_factory.services.runner_service import _concurrency_class_for_turn


def test_concurrency_class_from_runtime():
    rs = SimpleNamespace(runtime={"concurrency_class": "batch"})
    assert _concurrency_class_for_turn(rs, None) == "batch"


def test_concurrency_class_document_when_file_ids():
    rs = SimpleNamespace(runtime={})
    assert _concurrency_class_for_turn(rs, ["f1"]) == "document"


def test_concurrency_class_interactive_default():
    rs = SimpleNamespace(runtime={})
    assert _concurrency_class_for_turn(rs, None) == "interactive"


def test_concurrency_class_invalid_runtime_ignored():
    rs = SimpleNamespace(runtime={"concurrency_class": "nope"})
    assert _concurrency_class_for_turn(rs, None) == "interactive"
