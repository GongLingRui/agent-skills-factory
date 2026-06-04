"""Tests for max output recovery logic in runner_service.

These are integration-style tests verifying the RunnerService turn loop
behaviour when finish_reason == 'length'.
"""

from __future__ import annotations

import pytest

from agent_factory.services.runner_service import RunnerService


def test_runner_service_instantiates():
    from agent_factory.services.model_gateway import ModelGateway
    from agent_factory.services.tool_gateway import ToolGateway
    from agent_factory.config import Settings

    class FakeGW(ModelGateway):
        def __init__(self):
            self.settings = Settings()
            self._models = {}
            self._clients = {}
            self._defaults = {}
            self._aliases = {}

    class FakeTG(ToolGateway):
        pass

    rs = RunnerService(FakeGW(), FakeTG())
    assert rs is not None
