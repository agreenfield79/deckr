"""
migrate_mongo_phase3c.py
========================
One-shot Python script that executes all Phase 3C manual MongoDB migration
steps in the correct order. Safe to re-run — each step is idempotent.

Run from backend/ with venv active (MongoDB must be running, backend does NOT
need to be running):

    python migrate_mongo_phase3c.py

Steps executed (in dependency order):
    1. 3C.7  — Migrate pipeline_runs.stages[] → pipeline_stage_logs
    2. 3C.3  — Remove stages[], rename total_duration_seconds, backfill new fields
    3. 3C.1  — Rename agent_outputs → agent_edit_history, strip content field
    4. 3C.2  — Drop workspaces collection
    5. 3C.4  — Strip SQL-duplicate fields from document_index
    6. Indexes — Create all Phase 2B indexes on new/renamed collections
"""

import os
import sys
from uuid import uuid4
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGODB_DB",  "deckr")

try:
    from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5_000)
    client.admin.command("ping")
    db = client[MONGO_DB]
except Exception as exc:
    print(f"\n  ✗  Cannot connect to MongoDB at {MONGO_URI}: {exc}")
    print("     Is MongoDB running? Check that MONGODB_URI in .env is correct.\n")
    sys.exit(1)

WIDTH = 68

def _banner(title: str) -> None:
    print(f"\n{'─' * WIDTH}")
    print(f"  {title}")
    print(f"{'─' * WIDTH}")

def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")

def _skip(msg: str) -> None:
    print(f"  –  {msg} (skipped — already done)")

def _warn(msg: str) -> None:
    print(f"  ⚠  {msg}")

collections = db.list_collection_names()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — 3C.7: Migrate pipeline_runs.stages[] → pipeline_stage_logs
# Must run BEFORE 3C.3 strips the stages field.
# ─────────────────────────────────────────────────────────────────────────────
_banner("Step 1 — 3C.7: Migrate pipeline_runs.stages[] → pipeline_stage_logs")

runs_with_stages = list(db.pipeline_runs.find(
    {"stages": {"$exists": True, "$not": {"$size": 0}}},
    {"pipeline_run_id": 1, "deal_id": 1, "stages": 1}
))

if not runs_with_stages:
    _skip("No pipeline_runs with embedded stages[] found")
else:
    inserted = 0
    skipped  = 0
    for run in runs_with_stages:
        run_id  = run.get("pipeline_run_id") or str(run["_id"])
        deal_id = run.get("deal_id") or ""
        for idx, stage in enumerate(run.get("stages") or []):
            # Idempotent: skip if already migrated (same run + agent_name + stage_order)
            agent_name  = stage.get("agent_name") or stage.get("name") or ""
            stage_order = stage.get("stage_order") if stage.get("stage_order") is not None else idx
            existing = db.pipeline_stage_logs.find_one({
                "pipeline_run_id": run_id,
                "agent_name":      agent_name,
                "stage_order":     stage_order,
            })
            if existing:
                skipped += 1
                continue

            elapsed_raw = stage.get("elapsed_ms")
            if elapsed_raw is None and stage.get("duration_seconds") is not None:
                elapsed_raw = int(stage["duration_seconds"] * 1000)

            db.pipeline_stage_logs.insert_one({
                "_id":                  str(uuid4()),
                "pipeline_run_id":      run_id,
                "deal_id":              deal_id,
                "agent_name":           agent_name,
                "stage_order":          stage_order,
                "status":               stage.get("status") or "complete",
                "started_at":           stage.get("started_at"),
                "completed_at":         stage.get("completed_at"),
                "elapsed_ms":           elapsed_raw,
                "error_message":        stage.get("error_message"),
                "tokens_used":          stage.get("tokens_used"),
                "model_id":             stage.get("model_id"),
                "cost_estimate_usd":    stage.get("cost_estimate_usd"),
                "context_docs_retrieved": stage.get("context_docs_retrieved"),
                "saved_to":             stage.get("saved_to") or stage.get("output_file_path"),
            })
            inserted += 1

    total_psl = db.pipeline_stage_logs.count_documents({})
    _ok(f"Inserted {inserted} new stage log records ({skipped} already existed). "
        f"pipeline_stage_logs total: {total_psl}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — 3C.3: Clean up pipeline_runs
# ─────────────────────────────────────────────────────────────────────────────
_banner("Step 2 — 3C.3: Clean up pipeline_runs")

# 2a. Remove embedded stages[]
result = db.pipeline_runs.update_many(
    {"stages": {"$exists": True}},
    {"$unset": {"stages": ""}}
)
if result.modified_count:
    _ok(f"Removed 'stages' field from {result.modified_count} pipeline_runs documents")
else:
    _skip("No pipeline_runs documents had 'stages' field")

# 2b. Rename total_duration_seconds → total_elapsed_ms
docs_with_old = list(db.pipeline_runs.find(
    {"total_duration_seconds": {"$exists": True}},
    {"total_duration_seconds": 1}
))
if docs_with_old:
    for doc in docs_with_old:
        old_val = doc.get("total_duration_seconds") or 0
        db.pipeline_runs.update_one(
            {"_id": doc["_id"]},
            {
                "$set":   {"total_elapsed_ms": int(old_val * 1000) if old_val else old_val},
                "$unset": {"total_duration_seconds": ""},
            }
        )
    _ok(f"Renamed total_duration_seconds → total_elapsed_ms on {len(docs_with_old)} documents")
else:
    _skip("total_duration_seconds not found — already renamed or field never existed")

# 2c. Backfill triggered_by and pipeline_version
result2 = db.pipeline_runs.update_many(
    {"triggered_by": {"$exists": False}},
    {"$set": {"triggered_by": "api", "pipeline_version": "v1.0"}}
)
if result2.modified_count:
    _ok(f"Backfilled triggered_by + pipeline_version on {result2.modified_count} documents")
else:
    _skip("triggered_by already present on all pipeline_runs documents")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — 3C.1: Rename agent_outputs → agent_edit_history
# ─────────────────────────────────────────────────────────────────────────────
_banner("Step 3 — 3C.1: Retire agent_outputs → agent_edit_history")

if "agent_edit_history" in db.list_collection_names():
    _skip("agent_edit_history already exists (rename already done)")
elif "agent_outputs" not in db.list_collection_names():
    _skip("Neither agent_outputs nor agent_edit_history found — nothing to migrate")
else:
    db.agent_outputs.rename("agent_edit_history")
    _ok("Renamed agent_outputs → agent_edit_history")

# Strip content field
result3 = db.agent_edit_history.update_many(
    {"content": {"$exists": True}},
    {"$unset": {"content": ""}}
)
if result3.modified_count:
    _ok(f"Removed 'content' field from {result3.modified_count} agent_edit_history documents")
else:
    _skip("No 'content' field found in agent_edit_history documents")

count_aeh = db.agent_edit_history.count_documents({})
_ok(f"agent_edit_history collection has {count_aeh} document(s)")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — 3C.2: Drop workspaces collection
# ─────────────────────────────────────────────────────────────────────────────
_banner("Step 4 — 3C.2: Retire workspaces collection")

if "workspaces" not in db.list_collection_names():
    _skip("workspaces collection already gone")
else:
    ws_count = db.workspaces.count_documents({})
    _warn(f"About to drop workspaces collection ({ws_count} documents). "
          "Ensure SQL workspaces table has matching rows.")
    db.workspaces.drop()
    _ok("Dropped workspaces collection")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — 3C.4: Strip SQL-duplicate fields from document_index
# ─────────────────────────────────────────────────────────────────────────────
_banner("Step 5 — 3C.4: Strip SQL-duplicate fields from document_index")

SQL_ONLY = ["file_size_bytes", "page_count", "extraction_status", "extracted_at"]

if "document_index" not in db.list_collection_names():
    _skip("document_index collection is empty / does not exist yet")
else:
    unset_payload = {f: "" for f in SQL_ONLY}
    result4 = db.document_index.update_many(
        {"$or": [{f: {"$exists": True}} for f in SQL_ONLY]},
        {"$unset": unset_payload}
    )
    if result4.modified_count:
        _ok(f"Stripped SQL-duplicate fields from {result4.modified_count} document_index documents")
    else:
        _skip("No SQL-duplicate fields found in document_index")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Create all Phase 2B indexes
# ─────────────────────────────────────────────────────────────────────────────
_banner("Step 6 — Create Phase 2B indexes")

def _ensure_index(collection_name: str, keys: list, **kwargs) -> None:
    """Create an index if it doesn't already exist. Fully idempotent."""
    try:
        coll = db[collection_name]
        coll.create_index(keys, **kwargs)
        key_desc = ", ".join(f"{k}:{v}" for k, v in keys)
        _ok(f"{collection_name}: index ({key_desc})")
    except Exception as exc:
        _warn(f"{collection_name} index failed: {exc}")

# agent_edit_history
_ensure_index("agent_edit_history",  [("deal_id", ASCENDING), ("agent_name", ASCENDING)])
_ensure_index("agent_edit_history",  [("pipeline_run_id", ASCENDING)])

# document_chunks
_ensure_index("document_chunks",     [("document_id", ASCENDING), ("chunk_index", ASCENDING)], unique=True)
_ensure_index("document_chunks",     [("deal_id", ASCENDING)])
_ensure_index("document_chunks",     [("text", TEXT)])

# rag_contexts
_ensure_index("rag_contexts",        [("pipeline_run_id", ASCENDING)])
_ensure_index("rag_contexts",        [("deal_id", ASCENDING)])

# pipeline_stage_logs
_ensure_index("pipeline_stage_logs", [("pipeline_run_id", ASCENDING)])
_ensure_index("pipeline_stage_logs", [("deal_id", ASCENDING)])
_ensure_index("pipeline_stage_logs", [("agent_name", ASCENDING)])

# news_articles
_ensure_index("news_articles",       [("url", ASCENDING)], unique=True)
_ensure_index("news_articles",       [("deal_id", ASCENDING)])
_ensure_index("news_articles",       [("headline", TEXT), ("body", TEXT)])

# court_filings
_ensure_index("court_filings",       [("neo4j_action_id", ASCENDING)], unique=True)
_ensure_index("court_filings",       [("deal_id", ASCENDING)])

# press_releases
_ensure_index("press_releases",      [("source_url", ASCENDING)], unique=True)
_ensure_index("press_releases",      [("deal_id", ASCENDING)])

# industry_reports
_ensure_index("industry_reports",    [("naics_code", ASCENDING), ("title", ASCENDING)], unique=True)
_ensure_index("industry_reports",    [("naics_code", ASCENDING)])

# reviews
_ensure_index("reviews",             [("deal_id", ASCENDING)])
_ensure_index("reviews",             [("entity_id", ASCENDING), ("platform", ASCENDING)])

# model_feedback
_ensure_index("model_feedback",      [("deal_id", ASCENDING)])
_ensure_index("model_feedback",      [("pipeline_run_id", ASCENDING)])

# prompt_versions
_ensure_index("prompt_versions",     [("agent_name", ASCENDING), ("version", ASCENDING)], unique=True)
_ensure_index("prompt_versions",     [("deployed_at", DESCENDING)])

# document_index
_ensure_index("document_index",      [("deal_id", ASCENDING)])
_ensure_index("document_index",      [("document_id", ASCENDING)], unique=True)


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'═' * WIDTH}")
print(f"  Phase 3C MongoDB Migration — complete")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"\n  Next step:")
print(f"    python seed_prompt_versions.py   ← seeds prompt_versions collection")
print(f"    python verify_mongo_phase3c.py   ← verify all Phase 3C requirements")
print(f"{'═' * WIDTH}\n")
