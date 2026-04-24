"""
MongoDB Service — document index, agent edit history, pipeline run cache,
external evidence corpus, RAG context capture, ML layer.

D-3: all operations catch exceptions and return None/False/[] rather than raising.
Phase 3C implementation — aligned with Phase 2B target schema.
"""

import hashlib
import logging
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger("deckr.mongo_service")

# ---------------------------------------------------------------------------
# Retry decorator — mirrors sql_service._sql_retry pattern (P-3)
# ---------------------------------------------------------------------------

try:
    from tenacity import (
        retry as _tenacity_retry,
        stop_after_attempt,
        wait_exponential,
    )

    def _mongo_retry(fn):
        """Wrap a callable with 3-attempt exponential-backoff retry on any exception."""
        return _tenacity_retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            reraise=True,
        )(fn)

except ImportError:
    def _mongo_retry(fn):
        """No-op fallback if tenacity is not installed."""
        return fn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _db():
    from services.db_factory import get_mongo_db
    return get_mongo_db()


# ---------------------------------------------------------------------------
# document_index — one doc per uploaded file (Group B, Phase 2B)
# Boundary rule: never write SQL-owned fields (file_size_bytes, page_count,
# extraction_status, extracted_at). Those belong in SQL documents table only.
# ---------------------------------------------------------------------------

@_mongo_retry
def index_document(workspace_id: str, deal_id: str, document_id: str,
                   file_name: str, file_path: str, document_type: str,
                   entity_id: str | None = None,
                   content_hash: str | None = None) -> bool:
    """Insert or update a document index entry. SQL-owned fields are never written."""
    try:
        db = _db()
        if db is None:
            return False
        db.document_index.update_one(
            {"document_id": document_id},
            {
                "$set": {
                    "document_id":    document_id,
                    "workspace_id":   workspace_id,
                    "deal_id":        deal_id,
                    "entity_id":      entity_id,
                    "file_name":      file_name,
                    "file_path":      file_path,
                    "document_type":  document_type,
                    "content_hash":   content_hash,
                    "indexed_at":     _now().isoformat(),
                    "updated_at":     _now().isoformat(),
                },
                "$setOnInsert": {"_id": document_id},
            },
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("index_document failed: %s", exc)
        return False


def get_document_metadata(deal_id: str | None = None) -> list[dict]:
    """Return document_index docs for a deal, with agent read badges."""
    try:
        db = _db()
        if db is None:
            return []
        query = {"deal_id": deal_id} if deal_id else {}
        docs = list(db.document_index.find(query, {"_id": 0}).sort("indexed_at", -1))
        return docs
    except Exception as exc:
        logger.warning("get_document_metadata failed: %s", exc)
        return []


@_mongo_retry
def mark_document_read_by_agent(document_id: str, agent_name: str) -> bool:
    """Record that an agent has read a document (agents_read array)."""
    try:
        db = _db()
        if db is None:
            return False
        db.document_index.update_one(
            {"document_id": document_id},
            {
                "$addToSet": {"agents_read": agent_name},
                "$set":      {"updated_at": _now().isoformat()},
            },
        )
        return True
    except Exception as exc:
        logger.warning("mark_document_read_by_agent failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# document_chunks — raw text chunks from uploaded PDFs (Group B, Phase 2B)
# No embedding field — vectors are in ChromaDB (local) or pgvector (cloud).
# ---------------------------------------------------------------------------

@_mongo_retry
def save_document_chunk(document_id: str, deal_id: str, entity_id: str,
                        file_name: str, page_number: int, chunk_index: int,
                        chunk_type: str, text: str) -> bool:
    """
    Persist one text chunk from an extracted PDF.
    chunk_type: paragraph | table | header | footnote
    Indexes created on first write: {deal_id:1}, {document_id:1, chunk_index:1} unique, text {text}.
    """
    try:
        db = _db()
        if db is None:
            return False
        db.document_chunks.update_one(
            {"document_id": document_id, "chunk_index": chunk_index},
            {
                "$set": {
                    "document_id":  document_id,
                    "deal_id":      deal_id,
                    "entity_id":    entity_id,
                    "file_name":    file_name,
                    "page_number":  page_number,
                    "chunk_index":  chunk_index,
                    "chunk_type":   chunk_type,
                    "text":         text,
                    "char_count":   len(text),
                    "indexed_at":   _now().isoformat(),
                },
                "$setOnInsert": {"_id": str(uuid4())},
            },
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("save_document_chunk failed: %s", exc)
        return False


def get_document_chunks(document_id: str) -> list[dict]:
    """Return all chunks for a document, ordered by chunk_index."""
    try:
        db = _db()
        if db is None:
            return []
        return list(
            db.document_chunks.find(
                {"document_id": document_id}, {"_id": 0}
            ).sort("chunk_index", 1)
        )
    except Exception as exc:
        logger.warning("get_document_chunks failed: %s", exc)
        return []


def get_deal_chunks(deal_id: str) -> list[dict]:
    """Return all chunks for a deal, ordered by document then chunk_index."""
    try:
        db = _db()
        if db is None:
            return []
        return list(
            db.document_chunks.find(
                {"deal_id": deal_id}, {"_id": 0}
            ).sort([("document_id", 1), ("chunk_index", 1)])
        )
    except Exception as exc:
        logger.warning("get_deal_chunks failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# agent_edit_history — replaces agent_outputs (Group D, Phase 2B)
# Stores pointer + hash only — never the .md content (filesystem is source of truth).
# ---------------------------------------------------------------------------

@_mongo_retry
def save_agent_edit_history(deal_id: str, agent_name: str,
                            pipeline_run_id: str, output_path: str,
                            content: str, version: int = 1) -> bool:
    """
    Record that an agent wrote an output file.
    Stores SHA-256 hash of content only — not the content itself.
    The .md file on the filesystem is the source of truth.
    """
    try:
        db = _db()
        if db is None:
            return False
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        db.agent_edit_history.insert_one({
            "_id":                  str(uuid4()),
            "deal_id":              deal_id,
            "agent_name":           agent_name,
            "pipeline_run_id":      pipeline_run_id,
            "version":              version,
            "output_path":          output_path,
            "original_content_hash": content_hash,
            "saved_at":             _now().isoformat(),
            "edited_at":            None,
            "edited_by":            None,
            "diff_summary":         None,
        })
        return True
    except Exception as exc:
        logger.warning("save_agent_edit_history failed: %s", exc)
        return False


def get_agent_edit_history(deal_id: str, agent_name: str) -> list[dict]:
    """Return all edit history records for a deal + agent, newest first."""
    try:
        db = _db()
        if db is None:
            return []
        return list(
            db.agent_edit_history.find(
                {"deal_id": deal_id, "agent_name": agent_name},
                {"_id": 0},
            ).sort("saved_at", -1)
        )
    except Exception as exc:
        logger.warning("get_agent_edit_history failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# pipeline_runs — MongoDB cache (SQL is authoritative; this is a read cache)
# Phase 2B: no embedded stages[] — stages go to pipeline_stage_logs.
# ---------------------------------------------------------------------------

@_mongo_retry
def open_pipeline_run(pipeline_run_id: str, deal_id: str,
                      workspace_id: str, total_stages: int,
                      triggered_by: str = "api",
                      pipeline_version: str = "v1.0") -> bool:
    """Open a new pipeline_runs document at the start of a run."""
    try:
        db = _db()
        if db is None:
            return False
        db.pipeline_runs.update_one(
            {"pipeline_run_id": pipeline_run_id},
            {
                "$set": {
                    "pipeline_run_id":  pipeline_run_id,
                    "deal_id":          deal_id,
                    "workspace_id":     workspace_id,
                    "status":           "running",
                    "total_stages":     total_stages,
                    "triggered_by":     triggered_by,
                    "pipeline_version": pipeline_version,
                    "started_at":       _now().isoformat(),
                    "updated_at":       _now().isoformat(),
                },
                "$setOnInsert": {"_id": pipeline_run_id},
            },
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("open_pipeline_run failed: %s", exc)
        return False


@_mongo_retry
def append_stage_to_run(pipeline_run_id: str, agent_name: str,
                        stage_order: int, status: str = "complete",
                        elapsed_ms: int = 0,
                        saved_to: str | None = None,
                        deal_id: str = "") -> bool:
    """
    Record one agent stage result. Writes to pipeline_stage_logs collection
    (Phase 2B — no longer pushes to pipeline_runs.stages[]).
    Also updates pipeline_runs.updated_at timestamp.
    """
    try:
        db = _db()
        if db is None:
            return False
        save_stage_log(
            pipeline_run_id=pipeline_run_id,
            deal_id=deal_id,
            agent_name=agent_name,
            stage_order=stage_order,
            status=status,
            started_at=None,
            completed_at=_now().isoformat(),
            elapsed_ms=elapsed_ms,
            error_message=None,
            tokens_used=None,
            model_id=None,
            cost_estimate_usd=None,
            context_docs_retrieved=[],
            saved_to=saved_to,
        )
        db.pipeline_runs.update_one(
            {"pipeline_run_id": pipeline_run_id},
            {"$set": {"updated_at": _now().isoformat()}},
        )
        return True
    except Exception as exc:
        logger.warning("append_stage_to_run failed: %s", exc)
        return False


@_mongo_retry
def close_pipeline_run(pipeline_run_id: str, status: str = "complete",
                       total_elapsed_ms: int = 0) -> bool:
    """Close the pipeline_runs document — set status + completed_at."""
    try:
        db = _db()
        if db is None:
            return False
        result = db.pipeline_runs.update_one(
            {"pipeline_run_id": pipeline_run_id},
            {"$set": {
                "status":           status,
                "total_elapsed_ms": total_elapsed_ms,
                "completed_at":     _now().isoformat(),
                "updated_at":       _now().isoformat(),
            }},
        )
        if result.modified_count == 0:
            logger.warning(
                "close_pipeline_run: no document matched pipeline_run_id=%s — "
                "open_pipeline_run may have failed silently at IP1",
                pipeline_run_id,
            )
        return True
    except Exception as exc:
        logger.warning("close_pipeline_run failed: %s", exc)
        return False


def get_pipeline_run_history(deal_id: str | None = None,
                              limit: int = 20) -> list[dict]:
    """
    Return recent pipeline runs, newest first. Optionally filter by deal_id.

    Each run is enriched with its stage records from pipeline_stage_logs
    (Phase 2B stores stages in a separate collection, not embedded in pipeline_runs).
    """
    try:
        db = _db()
        if db is None:
            return []
        query = {"deal_id": deal_id} if deal_id else {}
        docs = list(
            db.pipeline_runs.find(query, {"_id": 0})
            .sort("started_at", -1)
            .limit(limit)
        )

        # Join each run with its stage telemetry from pipeline_stage_logs.
        # Only the fields the frontend needs are projected to keep payloads small.
        _stage_projection = {
            "_id": 0,
            "agent_name": 1,
            "stage_order": 1,
            "status": 1,
            "elapsed_ms": 1,
            "started_at": 1,
            "completed_at": 1,
            "saved_to": 1,
        }
        for doc in docs:
            run_id = doc.get("pipeline_run_id")
            if run_id:
                stages = list(
                    db.pipeline_stage_logs
                    .find({"pipeline_run_id": run_id}, _stage_projection)
                    .sort("stage_order", 1)
                )
                doc["stages"] = stages
            else:
                doc["stages"] = []

        return docs
    except Exception as exc:
        logger.warning("get_pipeline_run_history failed: %s", exc)
        return []




# ---------------------------------------------------------------------------
# pipeline_stage_logs — per-stage telemetry (Group C, Phase 2B)
# Replaces pipeline_runs.stages[] embedded array.
# cache_pipeline_run() removed — 3E.2: dead code (never called from pipeline).
# open_pipeline_run() + close_pipeline_run() already satisfy Phase 2B spec.
# ---------------------------------------------------------------------------

@_mongo_retry
def save_stage_log(pipeline_run_id: str, deal_id: str, agent_name: str,
                   stage_order: int, status: str,
                   started_at: str | None, completed_at: str | None,
                   elapsed_ms: int | None,
                   error_message: str | None,
                   tokens_used: int | None,
                   model_id: str | None,
                   cost_estimate_usd: float | None,
                   context_docs_retrieved: list | None,
                   saved_to: str | None) -> bool:
    """
    Write one stage log document to pipeline_stage_logs.
    Full Phase 2B document shape — all 12 fields always written (None if unavailable).
    Indexes: {pipeline_run_id: 1}, {deal_id: 1}
    """
    try:
        db = _db()
        if db is None:
            return False
        db.pipeline_stage_logs.insert_one({
            "_id":                   str(uuid4()),
            "pipeline_run_id":       pipeline_run_id,
            "deal_id":               deal_id,
            "agent_name":            agent_name,
            "stage_order":           stage_order,
            "status":                status,
            "started_at":            started_at,
            "completed_at":          completed_at or _now().isoformat(),
            "elapsed_ms":            elapsed_ms,
            "error_message":         error_message,
            "tokens_used":           tokens_used,
            "model_id":              model_id,
            "cost_estimate_usd":     cost_estimate_usd,
            "context_docs_retrieved": context_docs_retrieved or [],
            "saved_to":              saved_to,
        })
        return True
    except Exception as exc:
        logger.warning("save_stage_log failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# rag_contexts — per-agent retrieval telemetry (Group D, Phase 2B)
# ---------------------------------------------------------------------------

@_mongo_retry
def save_rag_context(pipeline_run_id: str, deal_id: str, agent_name: str,
                     stage_order: int, query_text: str,
                     retrieved_chunks: list, final_prompt_hash: str | None = None,
                     completion_tokens: int | None = None) -> bool:
    """
    Capture RAG retrieval context for one agent invocation.
    retrieved_chunks: list of {chunk_id, document_id, file_name, chunk_index, score}
    Indexes: {pipeline_run_id: 1}, {deal_id: 1, agent_name: 1}
    """
    try:
        db = _db()
        if db is None:
            return False
        db.rag_contexts.insert_one({
            "_id":               str(uuid4()),
            "pipeline_run_id":   pipeline_run_id,
            "deal_id":           deal_id,
            "agent_name":        agent_name,
            "stage_order":       stage_order,
            "query_text":        query_text,
            "retrieved_chunks":  retrieved_chunks,
            "final_prompt_hash": final_prompt_hash,
            "completion_tokens": completion_tokens,
            "retrieved_at":      _now().isoformat(),
        })
        return True
    except Exception as exc:
        logger.warning("save_rag_context failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# External Evidence Corpus — Group A (Phase 2B, Step 3C.8)
# All write functions follow D-3 pattern: catch exceptions, log, return False.
# ---------------------------------------------------------------------------

@_mongo_retry
def save_news_article(deal_id: str, entity_ids: list[str],
                      headline: str, body: str, url: str,
                      source: str | None, publish_date: str | None,
                      sentiment_score: float | None = None,
                      keywords: list[str] | None = None,
                      entities_mentioned: list[str] | None = None) -> bool:
    """
    Persist a news article body to MongoDB.
    Upserted by URL (unique). Indexes: {deal_id:1}, {url:1} unique, text {headline,body}.
    """
    try:
        db = _db()
        if db is None:
            return False
        db.news_articles.update_one(
            {"url": url},
            {
                "$set": {
                    "deal_id":             deal_id,
                    "entity_ids":          entity_ids,
                    "headline":            headline,
                    "body":                body,
                    "url":                 url,
                    "source":              source,
                    "publish_date":        publish_date,
                    "sentiment_score":     sentiment_score,
                    "keywords":            keywords or [],
                    "entities_mentioned":  entities_mentioned or [],
                    "indexed_at":          _now().isoformat(),
                },
                "$setOnInsert": {"_id": str(uuid4())},
            },
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("save_news_article failed: %s", exc)
        return False


@_mongo_retry
def save_court_filing(deal_id: str, entity_ids: list[str],
                      neo4j_action_id: str, case_number: str,
                      court: str, filing_type: str, full_text: str,
                      filing_date: str | None = None,
                      parties: list[dict] | None = None,
                      outcome_summary: str | None = None) -> bool:
    """
    Persist a court filing full text to MongoDB.
    filing_type: complaint | motion | judgment | docket_entry
    Upserted by neo4j_action_id. Indexes: {deal_id:1}, {neo4j_action_id:1}, text {full_text}.
    """
    try:
        db = _db()
        if db is None:
            return False
        db.court_filings.update_one(
            {"neo4j_action_id": neo4j_action_id},
            {
                "$set": {
                    "deal_id":         deal_id,
                    "entity_ids":      entity_ids,
                    "neo4j_action_id": neo4j_action_id,
                    "case_number":     case_number,
                    "court":           court,
                    "filing_type":     filing_type,
                    "full_text":       full_text,
                    "filing_date":     filing_date,
                    "parties":         parties or [],
                    "outcome_summary": outcome_summary,
                    "indexed_at":      _now().isoformat(),
                },
                "$setOnInsert": {"_id": str(uuid4())},
            },
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("save_court_filing failed: %s", exc)
        return False


@_mongo_retry
def save_regulatory_action(deal_id: str, entity_ids: list[str],
                            agency: str, action_type: str,
                            full_text: str, summary: str,
                            amount: float | None = None,
                            effective_date: str | None = None,
                            resolution_date: str | None = None) -> bool:
    """
    Persist a regulatory action full text.
    agency: SEC | FDIC | OCC | FTC | state
    action_type: enforcement | consent_order | fine | cease_and_desist
    Indexes: {deal_id:1}, text {full_text, summary}.
    """
    try:
        db = _db()
        if db is None:
            return False
        db.regulatory_actions.insert_one({
            "_id":             str(uuid4()),
            "deal_id":         deal_id,
            "entity_ids":      entity_ids,
            "agency":          agency,
            "action_type":     action_type,
            "full_text":       full_text,
            "summary":         summary,
            "amount":          amount,
            "effective_date":  effective_date,
            "resolution_date": resolution_date,
            "indexed_at":      _now().isoformat(),
        })
        return True
    except Exception as exc:
        logger.warning("save_regulatory_action failed: %s", exc)
        return False


@_mongo_retry
def save_press_release(deal_id: str, entity_ids: list[str],
                       title: str, body: str, source_url: str,
                       published_at: str | None = None,
                       event_type: str | None = None) -> bool:
    """
    Persist a press release full text.
    event_type: earnings | M&A | leadership_change | product_launch | restructuring | funding
    Indexes: {deal_id:1}, text {title, body}.
    """
    try:
        db = _db()
        if db is None:
            return False
        db.press_releases.update_one(
            {"source_url": source_url},
            {
                "$set": {
                    "deal_id":      deal_id,
                    "entity_ids":   entity_ids,
                    "title":        title,
                    "body":         body,
                    "source_url":   source_url,
                    "published_at": published_at,
                    "event_type":   event_type,
                    "indexed_at":   _now().isoformat(),
                },
                "$setOnInsert": {"_id": str(uuid4())},
            },
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("save_press_release failed: %s", exc)
        return False


@_mongo_retry
def save_industry_report(naics_code: str, title: str, body: str,
                          published_at: str | None = None,
                          publisher: str | None = None,
                          report_type: str | None = None) -> bool:
    """
    Persist an industry report body. Scoped by naics_code — NOT deal_id.
    report_type: macro_outlook | sector_analysis | tariff_impact | geopolitical_risk
    Upserted by (naics_code, title). Indexes: {naics_code:1}, text {title, body}.
    """
    try:
        db = _db()
        if db is None:
            return False
        db.industry_reports.update_one(
            {"naics_code": naics_code, "title": title},
            {
                "$set": {
                    "naics_code":   naics_code,
                    "title":        title,
                    "body":         body,
                    "published_at": published_at,
                    "publisher":    publisher,
                    "report_type":  report_type,
                    "indexed_at":   _now().isoformat(),
                },
                "$setOnInsert": {"_id": str(uuid4())},
            },
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("save_industry_report failed: %s", exc)
        return False


@_mongo_retry
def save_review(deal_id: str, entity_id: str, platform: str,
                full_text: str, rating: float | None = None,
                review_date: str | None = None,
                reviewer_category: str | None = None,
                topics: list[str] | None = None,
                sentiment_score: float | None = None,
                response_text: str | None = None) -> bool:
    """
    Persist a business review full text.
    platform: BBB | Google | Yelp | Glassdoor | Trustpilot
    reviewer_category: customer | employee | vendor | anonymous
    Indexes: {deal_id:1}, {entity_id:1}, text {full_text}.
    NOTE: Stub — activate when BBB/Glassdoor API key is available.
    """
    try:
        db = _db()
        if db is None:
            return False
        db.reviews.insert_one({
            "_id":               str(uuid4()),
            "deal_id":           deal_id,
            "entity_id":         entity_id,
            "platform":          platform,
            "full_text":         full_text,
            "rating":            rating,
            "review_date":       review_date,
            "reviewer_category": reviewer_category,
            "topics":            topics or [],
            "sentiment_score":   sentiment_score,
            "response_text":     response_text,
            "indexed_at":        _now().isoformat(),
        })
        return True
    except Exception as exc:
        logger.warning("save_review failed: %s", exc)
        return False


def save_social_signal(*args, **kwargs) -> bool:
    """
    Compliance-gated — do not activate without ECOA/fair-lending review.
    LinkedIn and X API data collection requires explicit compliance sign-off
    and borrower opt-in before this function may be wired to any data source.
    """
    raise NotImplementedError(
        "social_signals requires compliance review before activation. "
        "See Phase 3C.8 compliance gate checklist."
    )


# ---------------------------------------------------------------------------
# AI/ML Layer — model_feedback and prompt_versions (Group D, Phase 2B)
# ---------------------------------------------------------------------------

@_mongo_retry
def save_model_feedback(deal_id: str, pipeline_run_id: str, agent_name: str,
                        prediction: str, human_correction: str,
                        correction_type: str, analyst_id: str) -> bool:
    """
    Record analyst correction for fine-tuning dataset accumulation.
    correction_type: factual | judgment | tone | omission | calculation
    Indexes: {agent_name:1}, {pipeline_run_id:1}.
    """
    try:
        db = _db()
        if db is None:
            return False
        db.model_feedback.insert_one({
            "_id":              str(uuid4()),
            "deal_id":          deal_id,
            "pipeline_run_id":  pipeline_run_id,
            "agent_name":       agent_name,
            "prediction":       prediction,
            "human_correction": human_correction,
            "correction_type":  correction_type,
            "feedback_at":      _now().isoformat(),
            "analyst_id":       analyst_id,
        })
        return True
    except Exception as exc:
        logger.warning("save_model_feedback failed: %s", exc)
        return False


@_mongo_retry
def upsert_prompt_version(agent_name: str, version: str,
                           prompt_template: str, model_id: str,
                           deployed_at: str | None = None,
                           deprecated_at: str | None = None,
                           performance_metrics: dict | None = None) -> bool:
    """
    Insert or update a prompt version record.
    Unique on (agent_name, version). Indexes: {agent_name:1, version:1} unique, {deployed_at:-1}.
    performance_metrics is None until real telemetry is available — do not hardcode.
    """
    try:
        db = _db()
        if db is None:
            return False
        db.prompt_versions.update_one(
            {"agent_name": agent_name, "version": version},
            {
                "$set": {
                    "agent_name":          agent_name,
                    "version":             version,
                    "prompt_template":     prompt_template,
                    "model_id":            model_id,
                    "deployed_at":         deployed_at or _now().isoformat(),
                    "deprecated_at":       deprecated_at,
                    "performance_metrics": performance_metrics,
                },
                "$setOnInsert": {"_id": str(uuid4())},
            },
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("upsert_prompt_version failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# External Evidence Helpers — 3E.2
# ---------------------------------------------------------------------------

def get_external_evidence_text(deal_id: str) -> str:
    """
    Return concatenated text from all external evidence collections for a deal.
    Queries: news_articles (body), reviews (full_text), court_filings (full_text),
             document_chunks (text). Also includes industry_reports keyed by naics_code
             if the deal's naics_code can be resolved from SQL.
    Used by word cloud endpoint and agent RAG context enrichment.
    Returns empty string on any failure (D-3).
    """
    try:
        db = _db()
        if db is None:
            return ""

        parts: list[str] = []

        # news_articles — body text
        try:
            for doc in db.news_articles.find({"deal_id": deal_id}, {"body": 1, "_id": 0}):
                if doc.get("body"):
                    parts.append(doc["body"])
        except Exception as exc:
            logger.warning("get_external_evidence_text: news_articles failed: %s", exc)

        # reviews — full_text
        try:
            for doc in db.reviews.find({"deal_id": deal_id}, {"full_text": 1, "_id": 0}):
                if doc.get("full_text"):
                    parts.append(doc["full_text"])
        except Exception as exc:
            logger.warning("get_external_evidence_text: reviews failed: %s", exc)

        # court_filings — full_text
        try:
            for doc in db.court_filings.find({"deal_id": deal_id}, {"full_text": 1, "_id": 0}):
                if doc.get("full_text"):
                    parts.append(doc["full_text"])
        except Exception as exc:
            logger.warning("get_external_evidence_text: court_filings failed: %s", exc)

        # regulatory_actions — full_text
        try:
            for doc in db.regulatory_actions.find({"deal_id": deal_id}, {"full_text": 1, "_id": 0}):
                if doc.get("full_text"):
                    parts.append(doc["full_text"])
        except Exception as exc:
            logger.warning("get_external_evidence_text: regulatory_actions failed: %s", exc)

        # press_releases — body
        try:
            for doc in db.press_releases.find({"deal_id": deal_id}, {"body": 1, "_id": 0}):
                if doc.get("body"):
                    parts.append(doc["body"])
        except Exception as exc:
            logger.warning("get_external_evidence_text: press_releases failed: %s", exc)

        # document_chunks — text
        try:
            for doc in db.document_chunks.find({"deal_id": deal_id}, {"text": 1, "_id": 0}):
                if doc.get("text"):
                    parts.append(doc["text"])
        except Exception as exc:
            logger.warning("get_external_evidence_text: document_chunks failed: %s", exc)

        # industry_reports — body (keyed by naics_code from SQL)
        try:
            from services import sql_service as _sql_ev
            from models.sql_models import Deal
            from services.db_factory import get_sql_session
            from sqlalchemy import select as _select
            with next(get_sql_session()) as _sess:
                deal_row = _sess.execute(
                    _select(Deal).where(Deal.deal_id == deal_id).limit(1)
                ).scalar_one_or_none()
            if deal_row and deal_row.naics_code:
                for doc in db.industry_reports.find(
                    {"naics_code": deal_row.naics_code}, {"body": 1, "_id": 0}
                ):
                    if doc.get("body"):
                        parts.append(doc["body"])
        except Exception as exc:
            logger.warning("get_external_evidence_text: industry_reports failed: %s", exc)

        return "\n\n".join(parts)
    except Exception as exc:
        logger.warning("get_external_evidence_text failed: %s", exc)
        return ""
