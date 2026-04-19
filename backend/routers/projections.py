"""
Projections Router — deterministic 3-statement projection model endpoints.
Rate-limited at 2/min per IP (consistent with /api/interpret/run).
"""

import logging

from fastapi import APIRouter, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("deckr.routers.projections")
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post("/run")
@limiter.limit("2/minute")
async def run_projections(request: Request):
    """
    Trigger the deterministic projections engine for a deal.
    Phase 4B stub — returns not_implemented until projections_service.py is fully wired.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    deal_id = body.get("deal_id")
    if not deal_id:
        return {"status": "error", "message": "deal_id required in request body"}

    from services.projections_service import run_projections as _run
    result = await _run(deal_id=deal_id,
                        workspace_root=body.get("workspace_root", ""),
                        pipeline_run_id=body.get("pipeline_run_id"))
    return result


@router.get("/output")
def get_projections_output(request: Request, deal_id: str | None = None):
    """
    Return projections.json and covenant_compliance.json for a deal.
    Reads from SQL projections + covenant_compliance_projections tables.
    Phase 4B stub.
    """
    if not deal_id:
        return {"status": "error", "message": "deal_id required"}
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Projection, CovenantComplianceProjection
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            proj_rows = session.execute(
                select(Projection).where(Projection.deal_id == deal_id)
                .order_by(Projection.scenario, Projection.projection_year)
            ).scalars().all()
            cov_rows = session.execute(
                select(CovenantComplianceProjection).where(
                    CovenantComplianceProjection.deal_id == deal_id
                ).order_by(
                    CovenantComplianceProjection.scenario,
                    CovenantComplianceProjection.projection_year,
                    CovenantComplianceProjection.covenant_type,
                )
            ).scalars().all()

        return {
            "deal_id": deal_id,
            "projections": [
                {
                    "scenario": r.scenario,
                    "year": r.projection_year,
                    "revenue": float(r.revenue or 0),
                    "ebitda": float(r.ebitda or 0),
                    "dscr": float(r.dscr) if r.dscr else None,
                    "funded_debt_to_ebitda": float(r.funded_debt_to_ebitda) if r.funded_debt_to_ebitda else None,
                    "free_cash_flow": float(r.free_cash_flow or 0),
                }
                for r in proj_rows
            ],
            "covenant_compliance": [
                {
                    "scenario": r.scenario,
                    "year": r.projection_year,
                    "covenant_type": r.covenant_type,
                    "computed_value": float(r.computed_value) if r.computed_value else None,
                    "threshold_value": float(r.threshold_value) if r.threshold_value else None,
                    "status": r.status,
                    "is_breach_year": r.is_breach_year,
                }
                for r in cov_rows
            ],
        }
    except Exception as exc:
        logger.warning("get_projections_output failed: %s", exc)
        return {"status": "error", "message": str(exc)}
