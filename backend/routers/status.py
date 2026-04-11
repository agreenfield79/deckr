import logging

from fastapi import APIRouter

from services import status_service

logger = logging.getLogger("deckr.routers.status")

router = APIRouter()


@router.get("")
def get_status():
    """Return the 10-item package completeness checklist and overall percentage."""
    return status_service.get_status()
