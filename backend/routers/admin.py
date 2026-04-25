"""
Admin Router — privileged pipeline management endpoints.

POST /api/admin/reset   Wipe all pipeline run data from every storage tier
                        and clear vector indexes. Gated by RESET_ENABLED=true.

Phase 0 notes implemented here:
  - Dialect-aware SQL clear (SQLite DELETE / PostgreSQL TRUNCATE ... CASCADE)
  - Dynamic table / collection discovery — no hardcoded lists
  - Active-run guard (HTTP 409) before any data deletion
  - Rate-limited: 3 requests / minute per IP
  - RESET_ENABLED flag must NOT be set in production Cloud Run revisions
"""

import logging
import os
import pathlib
import shutil

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from services.db_factory import get_mongo_db, get_neo4j_driver, get_sql_engine
from services.limiter import limiter

logger = logging.getLogger("deckr.routers.admin")

router = APIRouter()

# Path anchor: backend/ directory (two levels up from backend/routers/admin.py)
_BACKEND_ROOT = pathlib.Path(__file__).parent.parent

# Tables whose rows are never touched by reset (identity / configuration)
_SQL_PRESERVE = {
    "deals", "workspaces", "users", "sessions",
    "deal_access", "audit_log", "model_versions",
}


# ---------------------------------------------------------------------------
# Internal helpers — one per storage tier
# ---------------------------------------------------------------------------

def _reset_sql() -> str:
    """Clear all pipeline-data tables while preserving identity shells."""
    engine  = get_sql_engine()
    dialect = engine.dialect.name

    with engine.begin() as conn:
        if dialect == "sqlite":
            rows       = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            )
            all_tables = {row[0] for row in rows}
            to_clear   = all_tables - _SQL_PRESERVE
            if to_clear:
                # Disable FK enforcement so deletes succeed in any order
                conn.execute(text("PRAGMA foreign_keys = OFF"))
                for table in to_clear:
                    conn.execute(text(f"DELETE FROM \"{table}\""))
                conn.execute(text("PRAGMA foreign_keys = ON"))
        else:
            rows       = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                )
            )
            all_tables = {row[0] for row in rows}
            to_clear   = all_tables - _SQL_PRESERVE
            if to_clear:
                tables_sql = ", ".join(f'"{t}"' for t in to_clear)
                conn.execute(text(f"TRUNCATE {tables_sql} CASCADE"))

    cleared_label = "sqlite" if dialect == "sqlite" else "postgres"
    logger.info("admin/reset: SQL cleared (%s, %d table(s))", cleared_label, len(to_clear))
    return cleared_label


def _reset_mongo() -> None:
    """Delete all documents from every collection in the deckr database."""
    db = get_mongo_db()
    if db is None:
        logger.warning("admin/reset: MongoDB unavailable — skipping")
        return
    for cname in db.list_collection_names():
        db[cname].delete_many({})
    logger.info("admin/reset: MongoDB cleared")


def _reset_neo4j() -> None:
    """Detach-delete every node (and all relationships) from the graph."""
    driver = get_neo4j_driver()
    if driver is None:
        logger.warning("admin/reset: Neo4j unavailable — skipping")
        return
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    logger.info("admin/reset: Neo4j cleared")


def _reset_vectors() -> list[str]:
    """Remove Chroma directory and embeddings index file."""
    cleared: list[str] = []

    chroma_path     = _BACKEND_ROOT / "data" / ".chroma"
    embeddings_path = _BACKEND_ROOT / ".deckr_embeddings.json"

    if chroma_path.exists():
        shutil.rmtree(chroma_path)
        logger.info("admin/reset: Chroma vector store deleted (%s)", chroma_path)
        cleared.append("chroma")
    else:
        logger.debug("admin/reset: Chroma path not present — nothing to delete")
        cleared.append("chroma")  # still report as cleared (already empty)

    if embeddings_path.exists():
        embeddings_path.unlink()
        logger.info("admin/reset: Embeddings index deleted (%s)", embeddings_path)
        cleared.append("embeddings_index")
    else:
        logger.debug("admin/reset: Embeddings index not present — nothing to delete")
        cleared.append("embeddings_index")

    return cleared


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/reset")
@limiter.limit("3/minute")
def reset_pipeline_data(request: Request, confirm: bool = False, force: bool = False):
    """
    Wipe all pipeline run data across every storage tier.

    Query params:
      confirm=true   Required — prevents accidental resets.
      force=true     Optional — bypasses the active-run guard. Use when a prior
                     run is stuck in 'running' state (e.g. after a server restart).
                     Only meaningful in demo / dev revisions.

    Guards:
      RESET_ENABLED=true env flag   Returns HTTP 403 if absent.
      confirm=true                  Returns HTTP 400 if missing.
      No active pipeline runs       Returns HTTP 409 if a run is in progress
                                    (skipped when force=true).
    """
    # ── Guard 1: feature flag ──────────────────────────────────────────────
    if os.getenv("RESET_ENABLED", "false").lower() not in ("true", "1", "yes"):
        raise HTTPException(
            status_code=403,
            detail="Reset is not enabled. Set RESET_ENABLED=true in backend/.env.",
        )

    # ── Guard 2: explicit confirmation ────────────────────────────────────
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Add ?confirm=true to confirm the reset operation.",
        )

    # ── Guard 3: active-run check (skipped when force=true) ───────────────
    if not force:
        try:
            engine = get_sql_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT pipeline_run_id FROM pipeline_runs WHERE status = 'running' LIMIT 1")
                ).fetchone()
            if row:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A pipeline run is currently active. "
                        "Wait for completion or add ?force=true to override."
                    ),
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("admin/reset: active-run check failed (%s) — proceeding", exc)
    else:
        logger.warning("admin/reset: force=true — active-run guard bypassed")

    # ── Reset each tier ───────────────────────────────────────────────────
    cleared: list[str] = []
    errors:  list[str] = []

    try:
        sql_label = _reset_sql()
        cleared.append(sql_label)
    except Exception as exc:
        logger.error("admin/reset: SQL tier failed — %s", exc)
        errors.append(f"sql: {exc}")

    try:
        _reset_mongo()
        cleared.append("mongo")
    except Exception as exc:
        logger.error("admin/reset: MongoDB tier failed — %s", exc)
        errors.append(f"mongo: {exc}")

    try:
        _reset_neo4j()
        cleared.append("neo4j")
    except Exception as exc:
        logger.error("admin/reset: Neo4j tier failed — %s", exc)
        errors.append(f"neo4j: {exc}")

    try:
        vector_cleared = _reset_vectors()
        cleared.extend(vector_cleared)
    except Exception as exc:
        logger.error("admin/reset: Vector tier failed — %s", exc)
        errors.append(f"vectors: {exc}")

    # ── Broadcast SSE event ───────────────────────────────────────────────
    try:
        from services.event_bus import publish
        publish({"type": "pipeline_reset", "cleared": cleared})
    except Exception as exc:
        logger.warning("admin/reset: event_bus publish failed — %s", exc)

    return {
        "status":  "reset" if not errors else "partial",
        "cleared": cleared,
        **({"errors": errors} if errors else {}),
    }
