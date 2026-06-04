#!/usr/bin/env python3
"""对**已启动**的 HTTP 服务做 /health 轻量压测（P0.5 容量采样；非 CI 必跑）。

环境变量:
  BASE_URL         默认 http://127.0.0.1:8000
  CONCURRENCY      默认 32
  TOTAL_REQUESTS   默认 200

用法::

    cd backend && uv run uvicorn agent_factory.main:app --port 8000 &
    uv run python scripts/benchmark_health_smoke.py
"""
from __future__ import annotations

import asyncio
import os
import statistics
import time

import httpx


async def _main() -> int:
    base = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    conc = int(os.environ.get("CONCURRENCY", "32"))
    total = int(os.environ.get("TOTAL_REQUESTS", "200"))
    sem = asyncio.Semaphore(conc)
    latencies: list[float] = []

    async def one(client: httpx.AsyncClient) -> None:
        async with sem:
            t0 = time.perf_counter()
            r = await client.get(f"{base}/health")
            dt = time.perf_counter() - t0
            latencies.append(dt)
            r.raise_for_status()

    async with httpx.AsyncClient(timeout=30.0) as client:
        wall0 = time.perf_counter()
        await asyncio.gather(*(one(client) for _ in range(total)))
        wall = time.perf_counter() - wall0
    latencies.sort()
    p99 = latencies[int(0.99 * len(latencies)) - 1]
    print(
        f"requests={total} concurrency={conc} wall={wall:.2f}s "
        f"rps={total/wall:.1f} mean_ms={statistics.mean(latencies)*1000:.1f} "
        f"p99_ms={p99*1000:.1f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
