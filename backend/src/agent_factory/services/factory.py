"""Service factory for singletons (ModelGateway, ToolGateway, etc.)."""

from functools import lru_cache

from agent_factory.config import get_settings
from agent_factory.services.model_gateway import ModelGateway
from agent_factory.services.tool_gateway import ToolGateway


@lru_cache
def get_model_gateway() -> ModelGateway:
    return ModelGateway(get_settings())


@lru_cache
def get_tool_gateway() -> ToolGateway:
    return ToolGateway()
