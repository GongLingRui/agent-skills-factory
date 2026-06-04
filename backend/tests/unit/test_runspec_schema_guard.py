"""RunSpec schema version guard."""

import pytest

from agent_factory.core.runspec_schema import assert_runner_supports_runspec_version
from agent_factory.middleware.error_handler import AgentFactoryException


def test_runner_accepts_v1_v2() -> None:
    assert_runner_supports_runspec_version(1)
    assert_runner_supports_runspec_version(2)


def test_runner_rejects_v3() -> None:
    with pytest.raises(AgentFactoryException) as exc:
        assert_runner_supports_runspec_version(3)
    assert exc.value.code == "RUNSPEC_VERSION_UNSUPPORTED"
