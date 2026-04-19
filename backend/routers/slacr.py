"""
SLACR Router — component scores and SHAP/LIME explanation endpoints.
Reads from SQL slacr_scores table populated by IP3 hook in the pipeline.
"""

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger("deckr.routers.slacr")
router = APIRouter()


@router.get("/components")
def get_slacr_components(request: Request, deal_id: str | None = None):
    """Return S/L/A/C/R component scores + composite for the latest run of a deal."""
    try:
        if deal_id is None:
            return {"status": "error", "message": "deal_id required"}
        from services.db_factory import get_sql_session
        from models.sql_models import SlacrScore
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            row = session.execute(
                select(SlacrScore)
                .where(SlacrScore.deal_id == deal_id)
                .order_by(SlacrScore.computed_at.desc())
            ).scalars().first()
            if row is None:
                return {"deal_id": deal_id, "components": None}

            def _f(v):
                return float(v) if v is not None else None

            return {
                "deal_id": deal_id,
                "components": {
                    "sponsor_score":     _f(row.sponsor_score),
                    "leverage_score":    _f(row.leverage_score),
                    "asset_quality_score": _f(row.asset_quality_score),
                    "cash_flow_score":   _f(row.cash_flow_score),
                    "risk_score":        _f(row.risk_score),
                    "composite_score":   _f(row.composite_score),
                    "internal_rating":   row.internal_rating,
                    "occ_classification": row.occ_classification,
                    "model_version":     row.model_version,
                    "computed_at":       row.computed_at.isoformat() if row.computed_at else None,
                },
            }
    except Exception as exc:
        logger.warning("get_slacr_components failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/shap-lime")
def get_shap_lime(request: Request, deal_id: str | None = None):
    """Return SHAP waterfall + LIME local explanation values for the latest run."""
    try:
        if deal_id is None:
            return {"status": "error", "message": "deal_id required"}
        from services.db_factory import get_sql_session
        from models.sql_models import SlacrScore
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            row = session.execute(
                select(SlacrScore)
                .where(SlacrScore.deal_id == deal_id)
                .order_by(SlacrScore.computed_at.desc())
            ).scalars().first()
            if row is None:
                return {"deal_id": deal_id, "shap_values": None, "lime_values": None}
            return {
                "deal_id":     deal_id,
                "shap_values": row.shap_values,
                "lime_values": row.lime_values,
                "composite_score": float(row.composite_score) if row.composite_score else None,
                "internal_rating": row.internal_rating,
            }
    except Exception as exc:
        logger.warning("get_shap_lime failed: %s", exc)
        return {"status": "error", "message": str(exc)}
