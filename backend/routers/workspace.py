from fastapi import APIRouter

router = APIRouter()


@router.get("/tree")
def get_tree_stub():
    """Stub — implemented in Phase 2 (workspace_service.list_tree)."""
    return {"stub": True, "phase": "2", "items": []}
