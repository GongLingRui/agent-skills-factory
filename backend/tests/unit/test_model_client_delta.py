"""OpenAI delta parsing (MiniMax reasoning fields)."""

from agent_factory.infra.model_client import ModelClient


def test_parse_chunk_merges_reasoning_content_when_content_empty() -> None:
    client = ModelClient("http://127.0.0.1:9", "")
    chunk = client._parse_chunk(
        {
            "choices": [
                {
                    "delta": {"content": "", "reasoning_content": "step1"},
                    "finish_reason": None,
                }
            ]
        }
    )
    assert chunk.choices[0].delta == "step1"


def test_parse_chunk_concatenates_content_and_reasoning() -> None:
    client = ModelClient("http://127.0.0.1:9", "")
    chunk = client._parse_chunk(
        {
            "choices": [
                {
                    "delta": {
                        "content": "可见",
                        "reasoning_content": "",
                    },
                    "finish_reason": None,
                }
            ]
        }
    )
    assert chunk.choices[0].delta == "可见"


def test_parse_chunk_reasoning_details_list_text() -> None:
    client = ModelClient("http://127.0.0.1:9", "")
    chunk = client._parse_chunk(
        {
            "choices": [
                {
                    "delta": {
                        "content": "",
                        "reasoning_details": [{"text": "r1"}, {"text": "r2"}],
                    },
                    "finish_reason": None,
                }
            ]
        }
    )
    assert chunk.choices[0].delta == "r1r2"
