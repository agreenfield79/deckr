"""
MongoDB Service — document index, agent outputs, pipeline run cache.

D-3: all operations catch exceptions and return None/False rather than raising.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger("deckr.mongo_service")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _db():
    from services.db_factory import get_mongo_db
    return get_mongo_db()


# ---------------------------------------------------------------------------
# document_index — one doc per uploaded file
# ---------------------------------------------------------------------------

def index_document(workspace_id: str, deal_id: str, document_id: str,
                   file_name: str, file_path: str, document_type: str,
                   entity_id: str | None = None) -> bool:
    """Insert or update a document index entry."""
    try:
        db = _db()
        if db is None:
            return False
        db.document_index.update_one(
            {"document_id": document_id},
            {"$set": {
                "document_id": document_id,
                "workspace_id": workspace_id,
                "deal_id": deal_id,
                "entity_id": entity_id,
                "file_name": file_name,
                "file_path": file_path,
                "document_type": document_type,
                "indexed_at": _now().isoformat(),
            }},
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("index_document failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# agent_outputs — versioned agent markdown outputs
# ---------------------------------------------------------------------------

def save_agent_output(workspace_id: str, deal_id: str, pipeline_run_id: str,
                      agent_name: str, output_path: str, content: str) -> bool:
    """
    Store a versioned copy of an agent's markdown output.
    Multiple pipeline runs for the same deal accumulate — enables Run 1/2/3 version picker.
    """
    try:
        db = _db()
        if db is None:
            return False
        db.agent_outputs.insert_one({
            "_id": str(uuid4()),
            "workspace_id": workspace_id,
            "deal_id": deal_id,
            "pipeline_run_id": pipeline_run_id,
            "agent_name": agent_name,
            "output_path": output_path,
            "content": content,
            "saved_at": _now().isoformat(),
        })
        return True
    except Exception as exc:
        logger.warning("save_agent_output failed: %s", exc)
        return False


def get_agent_output_versions(deal_id: str, agent_name: str) -> list[dict]:
    """Return all versions of an agent output for a deal, newest first."""
    try:
        db = _db()
        if db is None:
            return []
        return list(
            db.agent_outputs.find(
                {"deal_id": deal_id, "agent_name": agent_name},
                {"_id": 0, "content": 0},  # exclude heavy content from listing
            ).sort("saved_at", -1)
        )
    except Exception as exc:
        logger.warning("get_agent_output_versions failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# pipeline_runs — MongoDB cache (SQL is authoritative; this is a read cache)
# ---------------------------------------------------------------------------

def open_pipeline_run(pipeline_run_id: str, deal_id: str,
                      workspace_id: str, total_stages: int) -> bool:
    """Open a new pipeline_runs document at the start of a run."""
    try:
        db = _db()
        if db is None:
            return False
        db.pipeline_runs.update_one(
            {"pipeline_run_id": pipeline_run_id},
            {"$set": {
                "pipeline_run_id": pipeline_run_id,
                "deal_id":         deal_id,
                "workspace_id":    workspace_id,
                "status":          "running",
                "total_stages":    total_stages,
                "stages":          [],
                "started_at":      _now().isoformat(),
                "updated_at":      _now().isoformat(),
            }},
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("open_pipeline_run failed: %s", exc)
        return False


def append_stage_to_run(pipeline_run_id: str, agent_name: str,
                        stage_order: int, status: str = "complete",
                        elapsed_ms: int = 0,
                        saved_to: str | None = None) -> bool:
    """Append one agent stage result to the pipeline_runs.stages[] array."""
    try:
        db = _db()
        if db is None:
            return False
        stage_doc = {
            "agent_name":  agent_name,
            "stage_order": stage_order,
            "status":      status,
            "elapsed_ms":  elapsed_ms,
            "saved_to":    saved_to,
            "completed_at": _now().isoformat(),
        }
        db.pipeline_runs.update_one(
            {"pipeline_run_id": pipeline_run_id},
            {
                "$push": {"stages": stage_doc},
                "$set":  {"updated_at": _now().isoformat()},
            },
        )
        return True
    except Exception as exc:
        logger.warning("append_stage_to_run failed: %s", exc)
        return False


def close_pipeline_run(pipeline_run_id: str, status: str = "complete",
                       total_elapsed_ms: int = 0) -> bool:
    """Close the pipeline_runs document — set status + completed_at."""
    try:
        db = _db()
        if db is None:
            return False
        db.pipeline_runs.update_one(
            {"pipeline_run_id": pipeline_run_id},
            {"$set": {
                "status":          status,
                "total_elapsed_ms": total_elapsed_ms,
                "completed_at":    _now().isoformat(),
                "updated_at":      _now().isoformat(),
            }},
        )
        return True
    except Exception as exc:
        logger.warning("close_pipeline_run failed: %s", exc)
        return False


def get_pipeline_run_history(deal_id: str | None = None,
                              limit: int = 20) -> list[dict]:
    """Return recent pipeline runs, newest first. Optionally filter by deal_id."""
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
        return docs
    except Exception as exc:
        logger.warning("get_pipeline_run_history failed: %s", exc)
        return []


def cache_pipeline_run(pipeline_run_id: str, deal_id: str,
                       workspace_id: str, status: str,
                       stages_completed: list | None = None) -> bool:
    try:
        db = _db()
        if db is None:
            return False
        db.pipeline_runs.update_one(
            {"pipeline_run_id": pipeline_run_id},
            {"$set": {
                "pipeline_run_id": pipeline_run_id,
                "deal_id": deal_id,
                "workspace_id": workspace_id,
                "status": status,
                "stages_completed": stages_completed or [],
                "updated_at": _now().isoformat(),
            }},
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("cache_pipeline_run failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# workspaces — workspace metadata cache
# ---------------------------------------------------------------------------

def upsert_workspace(workspace_id: str, project_path: str,
                     borrower_name: str | None = None) -> bool:
    try:
        db = _db()
        if db is None:
            return False
        db.workspaces.update_one(
            {"workspace_id": workspace_id},
            {"$set": {
                "workspace_id": workspace_id,
                "project_path": project_path,
                "borrower_name": borrower_name,
                "updated_at": _now().isoformat(),
            }, "$setOnInsert": {"created_at": _now().isoformat()}},
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.warning("upsert_workspace (mongo) failed: %s", exc)
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
                "$set": {"updated_at": _now().isoformat()},
            },
        )
        return True
    except Exception as exc:
        logger.warning("mark_document_read_by_agent failed: %s", exc)
        return False
