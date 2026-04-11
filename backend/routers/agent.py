from fastapi import APIRouter

router = APIRouter()


@router.get("/registry")
def get_registry_stub():
    """Stub — implemented in Phase 5 (agent_registry.list_agents)."""
    return {"stub": True, "phase": "5", "agents": []}
