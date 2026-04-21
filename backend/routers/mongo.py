"""
MongoDB Router — word cloud, document coverage, pipeline timeline endpoints.
Reads from MongoDB collections populated during the pipeline.

Phase 3C.10: Word cloud re-sourced to external evidence corpus
(news_articles, reviews, court_filings, document_chunks, industry_reports).
No longer reads from agent_outputs / agent_edit_history or filesystem .md files.
"""

import logging
import math
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
    Return top-60 terms by TF-weighted frequency from the External Evidence Corpus.

    Sources (Phase 3C.10):
      1. news_articles.body       — filtered by deal_id
      2. reviews.full_text        — filtered by deal_id
      3. court_filings.full_text  — filtered by deal_id
      4. document_chunks.text     — filtered by deal_id
      5. industry_reports.body    — filtered by naics_code from SQL deals table

    If all collections are empty, returns {"terms": [], "source": "no_evidence"}.
    No fallback to agent_edit_history or filesystem .md files.
    """
    try:
        if deal_id is None:
            return {"status": "error", "message": "deal_id required"}

        all_text: list[str] = []
        sources_used: list[str] = []

        from services.mongo_service import _db as _mongo_db
        db = _mongo_db()

        if db is not None:
            # Sources 1–4: deal-scoped collections
            _DEAL_SOURCES = [
                ("news_articles",   "body"),
                ("reviews",         "full_text"),
                ("court_filings",   "full_text"),
                ("document_chunks", "text"),
            ]
            for collection_name, field in _DEAL_SOURCES:
                try:
                    docs = list(
                        getattr(db, collection_name)
                        .find({"deal_id": deal_id}, {field: 1, "_id": 0})
                        .limit(100)
                    )
                    texts = [d[field] for d in docs if d.get(field)]
                    if texts:
                        all_text.extend(texts)
                        sources_used.append(collection_name)
                except Exception:
                    pass

            # Source 5: industry_reports — scoped by naics_code from SQL
            try:
                from services.db_factory import get_sql_session
                from models.sql_models import Deal
                from sqlalchemy import select
                with next(get_sql_session()) as session:
                    row = session.execute(
                        select(Deal.naics_code).where(Deal.deal_id == deal_id)
                    ).scalar_one_or_none()
                naics_code = row
                if naics_code:
                    docs = list(
                        db.industry_reports
                        .find({"naics_code": naics_code}, {"body": 1, "_id": 0})
                        .limit(10)
                    )
                    texts = [d["body"] for d in docs if d.get("body")]
                    if texts:
                        all_text.extend(texts)
                        sources_used.append("industry_reports")
            except Exception:
                pass

        if not all_text:
            return {"deal_id": deal_id, "terms": [], "source": "no_evidence"}

        # TF-IDF weighting (Phase 2B requirement)
        # Each entry in all_text is treated as one document.
        doc_token_lists = [_tokenize(t) for t in all_text]
        n_docs = len(doc_token_lists)

        # Document frequency: number of documents containing each term.
        df: Counter = Counter()
        for tokens in doc_token_lists:
            for term in set(tokens):
                df[term] += 1

        # Accumulate TF-IDF scores across all documents.
        tfidf: Counter = Counter()
        for tokens in doc_token_lists:
            if not tokens:
                continue
            tf = Counter(tokens)
            doc_len = len(tokens)
            for term, count in tf.items():
                tf_score = count / doc_len
                idf_score = math.log(n_docs / df[term]) + 1.0  # +1 prevents zero IDF when N==df
                tfidf[term] += tf_score * idf_score

        top = tfidf.most_common(60)
        max_score = top[0][1] if top else 1.0

        return {
            "deal_id": deal_id,
            "source":  sources_used,
            "terms": [
                {"text": word, "value": round(score, 6), "weight": round(score / max_score, 4)}
                for word, score in top
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
    Note: SQL pipeline_stage_logs has 79+ rows (actively written — not a fallback only).
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
                    "total_elapsed_ms": getattr(run, "total_elapsed_ms", None) or (getattr(run, "total_duration_seconds", 0) or 0) * 1000,
                    "stages": [
                        {
                            "agent_name": s.agent_name,
                            "stage_order": s.stage_order,
                            "status": s.status,
                            "elapsed_ms": getattr(s, "elapsed_ms", None) or (getattr(s, "duration_seconds", 0) or 0) * 1000,
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
