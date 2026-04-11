import logging

from fastapi import APIRouter, HTTPException

from models.slacr import SlacrInput, SlacrOutput
from services import slacr_service

logger = logging.getLogger("deckr.routers.risk")

router = APIRouter()


@router.post("/score")
def post_score(body: SlacrInput) -> SlacrOutput:
    """Compute weighted SLACR score from analyst inputs and persist to SLACR/slacr.json."""
    output = slacr_service.compute(body)
    slacr_service.save(output)
    logger.info("POST /risk/score: saved (score=%.2f %s)", output.weighted_score, output.rating)
    return output


@router.get("/score")
def get_score() -> SlacrOutput:
    """Return the most recently saved SLACR score from SLACR/slacr.json."""
    result = slacr_service.load()
    if result is None:
        raise HTTPException(status_code=404, detail="No SLACR score found. Score the deal first.")
    return result
