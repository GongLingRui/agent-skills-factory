"""API v1 aggregate router."""

from fastapi import APIRouter

from agent_factory import __version__
from agent_factory.api.v1.admin import router as admin_router
from agent_factory.api.v1.agent_router import router as agent_router_api
from agent_factory.api.v1.agent_registry import router as agent_registry_router
from agent_factory.api.v1.agents import router as agents_router
from agent_factory.api.v1.audit import router as audit_router
from agent_factory.api.v1.auth import router as auth_router
from agent_factory.api.v1.feedback import router as feedback_router
from agent_factory.api.v1.feishu import router as feishu_router
from agent_factory.api.v1.metrics_frontend import router as metrics_router
from agent_factory.api.v1.policies import router as policies_router
from agent_factory.api.v1.skills import router as skills_router
from agent_factory.api.v1.tools import router as tools_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(feishu_router, prefix="/feishu", tags=["feishu"])
api_v1_router.include_router(agents_router, prefix="/agents", tags=["agents"])
api_v1_router.include_router(
    agent_router_api,
    prefix="/agent-router",
    tags=["agent-router"],
)
api_v1_router.include_router(
    agent_registry_router,
    prefix="/agents",
    tags=["agent-registry"],
)
api_v1_router.include_router(feedback_router, tags=["feedback"])
api_v1_router.include_router(skills_router, prefix="/skills", tags=["skills"])
api_v1_router.include_router(policies_router, tags=["policies"])
api_v1_router.include_router(tools_router, prefix="/tools", tags=["tools"])
api_v1_router.include_router(metrics_router, tags=["metrics"])
api_v1_router.include_router(audit_router)
api_v1_router.include_router(admin_router)


@api_v1_router.get("/status", tags=["meta"])
async def api_status() -> dict[str, str]:
    """Contract sanity check for clients and smoke tests."""
    return {"api": "v1", "service": "agent-factory", "version": __version__}
