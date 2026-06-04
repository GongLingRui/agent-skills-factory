"""Doc parse job enqueue."""

import pytest

from agent_factory.infra.doc_queue import (
    STREAM_KEY,
    enqueue_doc_parse_job,
)


class _RedisCapture:
    def __init__(self) -> None:
        self.xadd_calls: list[tuple[str, dict[str, str]]] = []

    async def xadd(self, stream: str, fields: dict[str, str]):
        self.xadd_calls.append((stream, fields))
        return "1-0"


@pytest.mark.asyncio
async def test_enqueue_puts_stream():
    cap = _RedisCapture()
    await enqueue_doc_parse_job(
        file_id="file_abc",
        file_size=11_000_000,
        redis=cap,
    )
    assert len(cap.xadd_calls) == 1
    stream, fields = cap.xadd_calls[0]
    assert stream == STREAM_KEY
    assert fields["file_id"] == "file_abc"
    assert fields["size"] == "11000000"
