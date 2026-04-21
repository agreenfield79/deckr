"""
fix_pipeline_runs_id.py
=======================
One-time backfill: sets _id = pipeline_run_id on pre-existing pipeline_runs
documents where MongoDB assigned an ObjectId instead of the UUID string.

MongoDB does not allow updating _id in place. This script deletes each
mismatched document and re-inserts it with the correct _id. Safe to re-run
(idempotent — documents already fixed are skipped).

Run from backend/ with venv active:
    python fix_pipeline_runs_id.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGODB_DB",  "deckr")

try:
    from pymongo import MongoClient
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5_000)
    client.admin.command("ping")
    db = client[MONGO_DB]
except Exception as exc:
    print(f"\n  ✗  Cannot connect to MongoDB: {exc}\n")
    sys.exit(1)

print(f"\nConnected to {MONGO_DB} — scanning pipeline_runs for _id mismatches...\n")

fixed   = 0
skipped = 0
failed  = 0

for doc in db.pipeline_runs.find({}):
    run_id = doc.get("pipeline_run_id")
    if not run_id:
        print(f"  ⚠  Document {doc['_id']} has no pipeline_run_id — skipping")
        skipped += 1
        continue

    if str(doc["_id"]) == str(run_id):
        skipped += 1
        continue  # Already correct — skip silently

    print(f"  Fixing: _id={doc['_id']}  →  _id={run_id}")

    # Build corrected document with _id = pipeline_run_id
    corrected = {k: v for k, v in doc.items() if k != "_id"}
    corrected["_id"] = run_id

    try:
        # Check if a doc with the target _id already exists (idempotency)
        if db.pipeline_runs.find_one({"_id": run_id}):
            print(f"    – Target _id={run_id} already exists — removing old ObjectId doc only")
            db.pipeline_runs.delete_one({"_id": doc["_id"]})
        else:
            db.pipeline_runs.delete_one({"_id": doc["_id"]})
            db.pipeline_runs.insert_one(corrected)
        fixed += 1
        print(f"    ✓ Fixed")
    except Exception as exc:
        print(f"    ✗ Failed: {exc}")
        failed += 1

print(f"\n{'═' * 50}")
print(f"  Fixed:   {fixed}")
print(f"  Skipped: {skipped}  (already correct)")
print(f"  Failed:  {failed}")
print(f"{'═' * 50}\n")

if failed:
    sys.exit(1)
