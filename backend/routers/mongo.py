"""
MongoDB Router — word cloud, document coverage, pipeline timeline endpoints.
Reads from MongoDB collections populated during the pipeline.
"""

import logging
import re
from collections import Counter

from fastapi import APIRouter, Request

logger = logging.getLogger("deckr.routers.mongo")
router = APIRouter()

_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "has", "have", "had", "will", "would", "could", "should", "may", "might",
    "this", "that", "these", "those", "it", "its", "as", "not", "no", "if",
    "than", "then", "so", "yet", "both", "either", "each", "their", "our",
    "its", "he", "she", "they", "we", "you", "i", "my", "your", "his", "her",
    "all", "more", "also", "very", "just", "about", "over", "into", "after",
    "before", "through", "during", "however", "therefore", "including",
    "between", "against", "within", "without", "across", "such", "which",
    "who", "what", "how", "when", "where", "can", "do", "does", "did", "any",
    "while", "well", "new", "has", "one", "two", "three", "per", "based",
}


def _tokenize(text: str) -> list[str]:
    """Extract meaningful words from markdown text."""
    text = re.sub(r"#+\s*|[*_`#\[\]()>|~]", " ", text)
    tokens = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
    return [t for t in tokens if t not in _STOP_WORDS]


@router.get("/word-cloud")
def get_word_cloud(request: Request, deal_id: str | None = None):
    """
    Return top-60 terms by frequency across all agent .md outputs for a deal.
    Falls back to workspace .md files when MongoDB agent_outputs is empty.
    """
    try:
        if deal_id is None:
            return {"status": "error", "message": "deal_id required"}

        all_text: list[str] = []

        # Primary: MongoDB agent_outputs
        try:
            from services.mongo_service import _db as _mongo_db
            db = _mongo_db()
            if db is not None:
                docs = list(db.agent_outputs.find(
                    {"deal_id": deal_id},
                    {"content": 1, "_id": 0}
                ).limit(50))
                for doc in docs:
                    if doc.get("content"):
                        all_text.append(doc["content"])
        except Exception:
            pass

        # Fallback: read workspace .md files if no MongoDB data
        if not all_text:
            try:
                from services import workspace_service
                for folder in ["Agent Notes", "Deck", "SLACR"]:
                    try:
                        entries = workspace_service.list_files(folder)
                        for entry in (entries or []):
                            if entry.endswith(".md"):
                                content = workspace_service.read_file(entry)
                                if content:
                                    all_text.append(content)
                    except Exception:
                        pass
            except Exception:
                pass

        if not all_text:
            return {"deal_id": deal_id, "terms": []}

        combined = " ".join(all_text)
        tokens = _tokenize(combined)
        freq = Counter(tokens)
        top = freq.most_common(60)
        max_count = top[0][1] if top else 1

        return {
            "deal_id": deal_id,
            "terms": [
                {"text": word, "value": count, "weight": round(count / max_count, 4)}
                for word, count in top
            ],
        }
    except Exception as exc:
        logger.warning("get_word_cloud failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/document-coverage")
def get_document_coverage(request: Request, deal_id: str | None = None):
    """
    Return agent × document read matrix from document_index.agents_read.
    """
    try:
        if deal_id is None:
            return {"status": "error", "message": "deal_id required"}
        from services.mongo_service import get_document_metadata
        docs = get_document_metadata(deal_id)

        agents = [
            "extraction", "financial", "industry", "collateral",
            "guarantor", "risk", "interpreter", "packaging", "review", "deckr",
        ]
        matrix = []
        for doc in docs:
            agents_read = doc.get("agents_read") or []
            matrix.append({
                "document": doc.get("file_name", ""),
                "document_type": doc.get("document_type", ""),
                "coverage": {agent: agent in agents_read for agent in agents},
            })
        return {
            "deal_id": deal_id,
            "agents": agents,
            "documents": matrix,
        }
    except Exception as exc:
        logger.warning("get_document_coverage failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/pipeline-timeline")
def get_pipeline_timeline(request: Request, deal_id: str | None = None, limit: int = 5):
    """
    Return stage start/end/status per run for Gantt rendering.
    Sources MongoDB pipeline_runs first, falls back to SQL pipeline_stage_logs.
    """
    try:
        from services.mongo_service import get_pipeline_run_history
        runs = get_pipeline_run_history(deal_id, limit=limit)

        if runs:
            return {"deal_id": deal_id, "runs": runs, "source": "mongo"}

        # SQL fallback
        from services.db_factory import get_sql_session
        from models.sql_models import PipelineRun, PipelineStageLog
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            q = select(PipelineRun)
            if deal_id:
                q = q.where(PipelineRun.deal_id == deal_id)
            sql_runs = session.execute(
                q.order_by(PipelineRun.started_at.desc()).limit(limit)
            ).scalars().all()

            result = []
            for run in sql_runs:
                stages_q = select(PipelineStageLog).where(
                    PipelineStageLog.pipeline_run_id == run.pipeline_run_id
                ).order_by(PipelineStageLog.stage_order)
                stages = session.execute(stages_q).scalars().all()
                result.append({
                    "pipeline_run_id": run.pipeline_run_id,
                    "deal_id": run.deal_id,
                    "status": run.status,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                    "total_elapsed_ms": (run.total_duration_seconds or 0) * 1000,
                    "stages": [
                        {
                            "agent_name": s.agent_name,
                            "stage_order": s.stage_order,
                            "status": s.status,
                            "elapsed_ms": (s.duration_seconds or 0) * 1000,
                            "started_at": s.started_at.isoformat() if s.started_at else None,
                            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                        }
                        for s in stages
                    ],
                })
            return {"deal_id": deal_id, "runs": result, "source": "sql"}
    except Exception as exc:
        logger.warning("get_pipeline_timeline failed: %s", exc)
        return {"status": "error", "message": str(exc)}
