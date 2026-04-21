"""
verify_mongo_phase3c.py
=======================
Verification script for Phase 3C MongoDB Refactor.
Run AFTER completing all manual MongoDB migration steps (3C.1–3C.9).

Usage (venv active, from backend/):
    python verify_mongo_phase3c.py

Prints a pass/fail table for every Phase 3C requirement.
Exit code 0 = all checks pass. Exit code 1 = one or more checks fail.
"""

import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Bootstrap — allow running without a full FastAPI startup
# ---------------------------------------------------------------------------
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGODB_DB",  "deckr")

try:
    from pymongo import MongoClient
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4_000)
    client.admin.command("ping")
    db = client[MONGO_DB]
    MONGO_OK = True
except Exception as exc:
    db = None
    MONGO_OK = False
    _mongo_err = str(exc)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
WIDTH = 70

def _header(title: str) -> None:
    print(f"\n{'─' * WIDTH}")
    print(f"  {title}")
    print(f"{'─' * WIDTH}")

results: list[tuple[str, bool, str]] = []

def chk(label: str, value: bool, note: str = "") -> bool:
    results.append((label, value, note))
    status = "PASS" if value else "FAIL"
    note_str = f"  ← {note}" if note else ""
    print(f"  {'[x]' if value else '[ ]'}  {label[:55]:<55} {status}{note_str}")
    return value


# ---------------------------------------------------------------------------
# 0. Connectivity
# ---------------------------------------------------------------------------
_header("0 — MongoDB Connectivity")
if not chk("MongoDB reachable", MONGO_OK, "" if MONGO_OK else _mongo_err):
    print("\n  ✗  Cannot connect to MongoDB — aborting.\n")
    sys.exit(1)

collections = db.list_collection_names()
chk("Database accessible", True, MONGO_DB)


# ---------------------------------------------------------------------------
# 3C.1 — agent_outputs retired → agent_edit_history
# ---------------------------------------------------------------------------
_header("3C.1 — agent_outputs → agent_edit_history")

has_edit_history = "agent_edit_history" in collections
has_agent_outputs = "agent_outputs" in collections

chk("agent_edit_history collection exists", has_edit_history)
chk("agent_outputs collection is GONE", not has_agent_outputs)

if has_edit_history:
    sample_with_content = db.agent_edit_history.count_documents({"content": {"$exists": True}})
    chk("No 'content' field in agent_edit_history docs", sample_with_content == 0,
        f"{sample_with_content} docs still have 'content'" if sample_with_content else "")

    idx_names = [i["name"] for i in db.agent_edit_history.list_indexes()]
    chk("agent_edit_history has deal_id+agent_name index",
        any("deal_id" in n and "agent_name" in n for n in idx_names),
        str(idx_names))
    chk("agent_edit_history has pipeline_run_id index",
        any("pipeline_run_id" in n for n in idx_names),
        str(idx_names))


# ---------------------------------------------------------------------------
# 3C.2 — workspaces collection retired
# ---------------------------------------------------------------------------
_header("3C.2 — workspaces collection retired")
chk("workspaces collection is GONE", "workspaces" not in collections)


# ---------------------------------------------------------------------------
# 3C.3 — pipeline_runs restructured
# ---------------------------------------------------------------------------
_header("3C.3 — pipeline_runs restructured")
has_pr = "pipeline_runs" in collections

if has_pr:
    total_runs = db.pipeline_runs.count_documents({})
    docs_with_stages = db.pipeline_runs.count_documents({"stages": {"$exists": True}})
    docs_with_old_duration = db.pipeline_runs.count_documents({"total_duration_seconds": {"$exists": True}})
    docs_missing_triggered_by = db.pipeline_runs.count_documents({"triggered_by": {"$exists": False}})
    docs_missing_pv = db.pipeline_runs.count_documents({"pipeline_version": {"$exists": False}})

    chk("pipeline_runs: no embedded 'stages' field", docs_with_stages == 0,
        f"{docs_with_stages}/{total_runs} still have stages" if docs_with_stages else "")
    chk("pipeline_runs: no 'total_duration_seconds' field", docs_with_old_duration == 0,
        f"{docs_with_old_duration}/{total_runs} still have old field" if docs_with_old_duration else "")
    chk("pipeline_runs: all docs have 'triggered_by'", docs_missing_triggered_by == 0,
        f"{docs_missing_triggered_by}/{total_runs} missing" if docs_missing_triggered_by else "")
    chk("pipeline_runs: all docs have 'pipeline_version'", docs_missing_pv == 0,
        f"{docs_missing_pv}/{total_runs} missing" if docs_missing_pv else "")

    # D5: _id should equal pipeline_run_id
    sample = db.pipeline_runs.find_one()
    if sample:
        id_matches = str(sample.get("_id")) == str(sample.get("pipeline_run_id", "__NONE__"))
        chk("pipeline_runs: _id equals pipeline_run_id (D5)",
            id_matches, f"_id={sample.get('_id')} vs pipeline_run_id={sample.get('pipeline_run_id')}")
else:
    chk("pipeline_runs collection exists", False, "collection not found")


# ---------------------------------------------------------------------------
# 3C.4 — document_index boundary
# ---------------------------------------------------------------------------
_header("3C.4 — document_index SQL boundary enforced")
has_di = "document_index" in collections

SQL_ONLY_FIELDS = ["file_size_bytes", "page_count", "extraction_status", "extracted_at"]

if has_di:
    total_di = db.document_index.count_documents({})
    for field in SQL_ONLY_FIELDS:
        count = db.document_index.count_documents({field: {"$exists": True}})
        chk(f"document_index: no '{field}' field", count == 0,
            f"{count}/{total_di} docs still have it" if count else "")

    # D7: _id should equal document_id
    sample_di = db.document_index.find_one()
    if sample_di:
        id_matches_di = str(sample_di.get("_id")) == str(sample_di.get("document_id", "__NONE__"))
        chk("document_index: _id equals document_id (D7)",
            id_matches_di, f"_id={sample_di.get('_id')} vs doc_id={sample_di.get('document_id')}")
else:
    chk("document_index collection exists", False, "collection not found — may be empty/new")


# ---------------------------------------------------------------------------
# 3C.5 — document_chunks
# ---------------------------------------------------------------------------
_header("3C.5 — document_chunks collection")
has_dc = "document_chunks" in collections
chk("document_chunks collection exists", has_dc)
if has_dc:
    idx_names_dc = [i["name"] for i in db.document_chunks.list_indexes()]
    chk("document_chunks: compound unique index (doc_id, chunk_index)",
        any("document_id" in n and "chunk_index" in n for n in idx_names_dc), str(idx_names_dc))
    chk("document_chunks: deal_id index", any("deal_id" in n for n in idx_names_dc), str(idx_names_dc))
    # Embedding field must NOT be in document_chunks (vectors go to pgvector/ChromaDB)
    docs_with_embedding = db.document_chunks.count_documents({"embedding": {"$exists": True}})
    chk("document_chunks: no 'embedding' field", docs_with_embedding == 0,
        f"{docs_with_embedding} docs have embedding — vectors must go to vector store only")


# ---------------------------------------------------------------------------
# 3C.6 — rag_contexts
# ---------------------------------------------------------------------------
_header("3C.6 — rag_contexts collection")
has_rc = "rag_contexts" in collections
chk("rag_contexts collection exists (created on first pipeline run)", has_rc,
    "will be created on first pipeline run after wiring (3E.7)" if not has_rc else "")
if has_rc:
    sample_rc = db.rag_contexts.find_one()
    if sample_rc:
        for field in ["pipeline_run_id", "deal_id", "agent_name", "stage_order",
                      "query_text", "retrieved_chunks", "final_prompt_hash",
                      "completion_tokens", "retrieved_at"]:
            chk(f"rag_contexts sample has '{field}'", field in sample_rc)


# ---------------------------------------------------------------------------
# 3C.7 — pipeline_stage_logs
# ---------------------------------------------------------------------------
_header("3C.7 — pipeline_stage_logs")
has_psl = "pipeline_stage_logs" in collections
chk("pipeline_stage_logs collection exists", has_psl)
if has_psl:
    psl_count = db.pipeline_stage_logs.count_documents({})
    chk("pipeline_stage_logs has migrated stage records", psl_count > 0, f"{psl_count} records")
    idx_names_psl = [i["name"] for i in db.pipeline_stage_logs.list_indexes()]
    chk("pipeline_stage_logs: pipeline_run_id index",
        any("pipeline_run_id" in n for n in idx_names_psl), str(idx_names_psl))
    chk("pipeline_stage_logs: deal_id index",
        any("deal_id" in n for n in idx_names_psl), str(idx_names_psl))
    # D3: new stage log docs should have non-empty deal_id (post-fix)
    if psl_count > 0:
        sample_psl = db.pipeline_stage_logs.find_one()
        if sample_psl:
            chk("pipeline_stage_logs sample has 'deal_id' field", "deal_id" in sample_psl)


# ---------------------------------------------------------------------------
# 3C.8 — external evidence collections
# ---------------------------------------------------------------------------
_header("3C.8 — External Evidence Corpus")
# Collections wired and indexed — expected to exist (even if empty).
for coll_name in ["news_articles", "court_filings", "press_releases",
                   "industry_reports", "reviews"]:
    exists = coll_name in collections
    count  = db[coll_name].count_documents({}) if exists else 0
    chk(f"{coll_name} collection exists", exists,
        f"{count} docs" if exists else "will populate on first enrichment run")

# regulatory_actions is DEFERRED — no API pass yet in enrichment_service.py.
# Treat as a known skip rather than a hard failure.
ra_exists = "regulatory_actions" in collections
ra_count  = db.regulatory_actions.count_documents({}) if ra_exists else 0
note_ra   = f"{ra_count} docs" if ra_exists else "deferred — no regulatory API pass yet (expected)"
print(f"  [–]  {'regulatory_actions (deferred)':<55} SKIP  ← {note_ra}")

# D1: verify court_filings _id is not in $set (behavioral — check existing docs)
if "court_filings" in collections:
    sample_cf = db.court_filings.find_one()
    if sample_cf:
        # If _id is a valid UUID string (not a BSON ObjectId), the D1 fix is in effect
        import bson
        chk("court_filings: _id is UUID string (not ObjectId)",
            isinstance(sample_cf.get("_id"), str),
            f"_id type={type(sample_cf.get('_id')).__name__}")


# ---------------------------------------------------------------------------
# 3C.9 — model_feedback and prompt_versions
# ---------------------------------------------------------------------------
_header("3C.9 — model_feedback + prompt_versions")
has_mf = "model_feedback" in collections
chk("model_feedback collection exists (created on first feedback write)", has_mf,
    "will be created on first frontend feedback call" if not has_mf else "")

has_pv = "prompt_versions" in collections
pv_count = db.prompt_versions.count_documents({}) if has_pv else 0
chk("prompt_versions collection seeded", has_pv and pv_count > 0,
    f"{pv_count} versions found — run 'python seed_prompt_versions.py' if 0" if has_pv else "run 'python seed_prompt_versions.py'")
if has_pv and pv_count > 0:
    sample_pv = db.prompt_versions.find_one()
    if sample_pv:
        chk("prompt_versions: performance_metrics is null on seed docs",
            sample_pv.get("performance_metrics") is None,
            f"value={sample_pv.get('performance_metrics')}")
        chk("prompt_versions: _id is UUID string (D4 fix)",
            isinstance(sample_pv.get("_id"), str),
            f"_id type={type(sample_pv.get('_id')).__name__}")


# ---------------------------------------------------------------------------
# 3C.11 — D-series fixes (spot-checks on existing documents)
# ---------------------------------------------------------------------------
_header("3C.11 — D-series bug fixes (spot-checks)")

# D2: document_chunks _id should be UUID (not ObjectId)
if "document_chunks" in collections:
    sample_dc2 = db.document_chunks.find_one()
    if sample_dc2:
        chk("document_chunks: _id is UUID string (D2 fix)",
            isinstance(sample_dc2.get("_id"), str),
            f"_id type={type(sample_dc2.get('_id')).__name__}")

# D4: news_articles _id should be UUID
if "news_articles" in collections:
    sample_na = db.news_articles.find_one()
    if sample_na:
        chk("news_articles: _id is UUID string (D4 fix)",
            isinstance(sample_na.get("_id"), str),
            f"_id type={type(sample_na.get('_id')).__name__}")

# D5: pipeline_runs — already checked above in 3C.3 section


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
passed = sum(1 for _, v, _ in results if v)
failed = sum(1 for _, v, _ in results if not v)
total  = len(results)

print(f"\n{'═' * WIDTH}")
print(f"  Phase 3C Verification — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"  {passed}/{total} checks passed  |  {failed} failed")
print(f"{'═' * WIDTH}\n")

if failed:
    print("  FAIL items to address:\n")
    for label, val, note in results:
        if not val:
            print(f"    ✗  {label}" + (f" — {note}" if note else ""))
    print()
    sys.exit(1)
else:
    print("  All Phase 3C checks passed.\n")
    sys.exit(0)
