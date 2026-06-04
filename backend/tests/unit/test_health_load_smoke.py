"""P0.5: lightweight concurrent /health load smoke (align docs/27 §性能测试)."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from agent_factory.main import create_app


@pytest.mark.asyncio
async def test_health_concurrent_asgi_smoke() -> None:
    """ASGI 层并发无失败；P99 在宽松阈值内（CI/本机，非外网 QPS 承诺）。"""
    app = create_app(enable_prometheus=False)
    transport = httpx.ASGITransport(app=app)
    n = 100
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=30.0
    ) as client:

        async def one() -> float:
            t0 = time.perf_counter()
            res = await client.get("/health")
            dt = time.perf_counter() - t0
            assert res.status_code == 200
            return dt

        latencies = await asyncio.gather(*(one() for _ in range(n)))
    assert len(latencies) == n
    latencies.sort()
    p99 = latencies[int(0.99 * n) - 1]
    assert p99 < 2.0, f"P99 latency {p99:.3f}s too high"
