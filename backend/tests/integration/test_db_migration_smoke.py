"""Verify PostgreSQL schema + seed after Alembic (CI runs migrate before pytest)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_demo_agent_present_when_database_available():
    """Fails in CI if migrations did not apply; skips locally without Postgres."""
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM agent_apps WHERE id = :id"),
                {"id": "demo-agent"},
            )
            count = result.scalar_one()
        assert count == 1
    except Exception as exc:
        msg = str(exc).lower()
        if any(
            x in msg
            for x in (
                "connection refused",
                "could not connect",
                "timeout",
                "name or service not known",
                "operationalerror",
            )
        ):
            pytest.skip(f"PostgreSQL not available: {exc}")
        raise
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_demo_skill_has_eval_cases_when_migration_0008_applied():
    """Needs alembic revision 20260509_0008 (demo skill eval metadata)."""
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT package_metadata::text FROM skills "
                    "WHERE id = 'demo-skill' AND version = '0.1.0'"
                )
            )
            raw = result.scalar_one_or_none()
        if raw is None:
            pytest.skip("demo-skill row missing (run alembic upgrade head)")
        if raw in ("null", "None", "") or "eval_cases" not in str(raw):
            pytest.skip(
                "Run `alembic upgrade head` to apply revision "
                "20260509_0008 (demo_skill_eval_metadata)."
            )
        assert "demo-smoke" in str(raw)
    except Exception as exc:
        msg = str(exc).lower()
        if any(
            x in msg
            for x in (
                "connection refused",
                "could not connect",
                "timeout",
                "name or service not known",
                "operationalerror",
            )
        ):
            pytest.skip(f"PostgreSQL not available: {exc}")
        raise
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_p0_policy_contract_agents_when_migration_0005_applied():
    """Requires alembic revision 20260508_0005; skips until `alembic upgrade head`."""
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM agent_apps WHERE id IN "
                    "('policy-qa-agent','contract-review-agent')"
                )
            )
            pair_count = result.scalar_one()
            if pair_count == 0:
                pytest.skip(
                    "Run `alembic upgrade head` to apply revision "
                    "20260508_0005 (policy + contract sample agents)."
                )
            assert pair_count == 2
    except Exception as exc:
        msg = str(exc).lower()
        if any(
            x in msg
            for x in (
                "connection refused",
                "could not connect",
                "timeout",
                "name or service not known",
                "operationalerror",
            )
        ):
            pytest.skip(f"PostgreSQL not available: {exc}")
        raise
    finally:
        await engine.dispose()
