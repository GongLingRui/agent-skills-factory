"""RunSpec schema version guard (docs/05, plan N=2)."""

from __future__ import annotations

from agent_factory.middleware.error_handler import AgentFactoryException

MIN_RUNSPEC_SCHEMA_VERSION = 1
# v1 and v2 share the same execution core; v3+ rejected until implemented.
MAX_RUNSPEC_SCHEMA_VERSION = 2


def assert_runner_supports_runspec_version(version: int) -> None:
    if version < MIN_RUNSPEC_SCHEMA_VERSION:
        raise AgentFactoryException(
            "INVALID_PARAMS",
            "runspec_schema_version must be >= 1",
            status_code=400,
        )
    if version > MAX_RUNSPEC_SCHEMA_VERSION:
        raise AgentFactoryException(
            "RUNSPEC_VERSION_UNSUPPORTED",
            (
                f"runspec_schema_version {version} exceeds supported window "
                f"(max {MAX_RUNSPEC_SCHEMA_VERSION})"
            ),
            status_code=400,
        )
