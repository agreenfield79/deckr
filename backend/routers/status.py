import logging

from fastapi import APIRouter

from services import status_service

logger = logging.getLogger("deckr.routers.status")

router = APIRouter()


@router.get("")
def get_status():
    """Return the 10-item package completeness checklist and overall percentage."""
    return status_service.get_status()


@router.get("/pipeline-history")
def get_pipeline_history(deal_id: str | None = None, limit: int = 20):
    """
    Return pipeline run history from MongoDB, newest first.
    Each entry includes: pipeline_run_id, deal_id, status, started_at,
    completed_at, total_elapsed_ms, and stages[].
    """
    try:
        from services import mongo_service
        runs = mongo_service.get_pipeline_run_history(deal_id=deal_id, limit=limit)
        # If MongoDB offline, fall back to SQL pipeline_stage_logs aggregate
        if not runs:
            try:
                from services.db_factory import get_sql_session
                from models.sql_models import PipelineRun
                from sqlalchemy import select
                with next(get_sql_session()) as session:
                    q = select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
                    if deal_id:
                        q = q.where(PipelineRun.deal_id == deal_id)
                    sql_runs = session.execute(q).scalars().all()
                    runs = [
                        {
                            "pipeline_run_id": r.pipeline_run_id,
                            "deal_id":         r.deal_id,
                            "workspace_id":    r.workspace_id,
                            "status":          r.status,
                            "started_at":      r.started_at.isoformat() if r.started_at else None,
                            "stages":          [],
                            "source":          "sql",
                        }
                        for r in sql_runs
                    ]
            except Exception as _sql_exc:
                logger.warning("pipeline-history SQL fallback failed: %s", _sql_exc)
        return {"runs": runs, "count": len(runs)}
    except Exception as exc:
        logger.warning("get_pipeline_history failed: %s", exc)
        return {"runs": [], "count": 0, "error": str(exc)}
