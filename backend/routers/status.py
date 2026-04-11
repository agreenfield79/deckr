from fastapi import APIRouter

router = APIRouter()


@router.get("")
def get_status_stub():
    """Stub — implemented in Phase 8 (status_service.get_status)."""
    return {"stub": True, "phase": "8", "items": [], "percentage": 0}
