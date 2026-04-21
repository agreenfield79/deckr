"""
seed_prompt_versions.py — Phase 3C.9

One-time seed script: reads each agent's system prompt file from the filesystem
and inserts a prompt_versions document into MongoDB with version = "v1.0".

Run with venv active from the backend/ directory:
    python seed_prompt_versions.py

Idempotent: upserts on (agent_name, version) — safe to re-run.
performance_metrics is initialized as None — populated by analytics once
real pipeline telemetry data accumulates. Do not hardcode metric values.
"""

import os
import sys
import pathlib
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("seed_prompt_versions")

# ---------------------------------------------------------------------------
# Agent registry — 11 agents with their system prompt paths and model IDs
# Mirrors agent_registry.py AGENTS dict (prompt file paths are relative to backend/)
# ---------------------------------------------------------------------------
AGENTS = [
    {"name": "guarantor",    "prompt": "prompts/guarantor_agent.txt",    "model": "granite"},
    {"name": "collateral",   "prompt": "prompts/collateral_agent.txt",   "model": "granite"},
    {"name": "industry",     "prompt": "prompts/industry_agent.txt",     "model": "granite"},
    {"name": "extraction",   "prompt": "prompts/extraction_agent.txt",   "model": "granite"},
    {"name": "packaging",    "prompt": "prompts/packaging_agent.txt",    "model": "llama-70b"},
    {"name": "financial",    "prompt": "prompts/financial_agent.txt",    "model": "granite"},
    {"name": "risk",         "prompt": "prompts/slacr_agent.txt",        "model": "granite"},
    {"name": "coordination", "prompt": "prompts/coordination_agent.txt", "model": "granite"},
    {"name": "review",       "prompt": "prompts/review_agent.txt",       "model": "llama-70b"},
    {"name": "deckr",        "prompt": "prompts/deckr_agent.txt",        "model": "llama-70b"},
    {"name": "interpreter",  "prompt": "prompts/interpreter_agent.txt",  "model": "llama-70b"},
]

BACKEND_DIR = pathlib.Path(__file__).parent


def _read_prompt(rel_path: str) -> str:
    """Read a prompt file. Returns empty string if not found."""
    full = BACKEND_DIR / rel_path
    if full.exists():
        return full.read_text(encoding="utf-8")
    logger.warning("Prompt file not found: %s — seeding with empty template", full)
    return ""


def main() -> None:
    # Ensure backend/ is on sys.path so service imports work
    sys.path.insert(0, str(BACKEND_DIR))

    # Load environment variables from .env if present
    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    from services.mongo_service import upsert_prompt_version, _db

    db = _db()
    if db is None:
        logger.error("MongoDB connection failed — check MONGO_URI in .env")
        sys.exit(1)

    deployed_at = datetime.now(timezone.utc).isoformat()
    seeded = 0
    skipped = 0

    for agent in AGENTS:
        prompt_text = _read_prompt(agent["prompt"])
        ok = upsert_prompt_version(
            agent_name=agent["name"],
            version="v1.0",
            prompt_template=prompt_text,
            model_id=agent["model"],
            deployed_at=deployed_at,
            deprecated_at=None,
            performance_metrics=None,  # populated by analytics layer once telemetry exists
        )
        if ok:
            logger.info("  ✓ %s  v1.0  (%d chars)", agent["name"], len(prompt_text))
            seeded += 1
        else:
            logger.warning("  ✗ %s  upsert failed", agent["name"])
            skipped += 1

    count = db.prompt_versions.count_documents({})
    logger.info("")
    logger.info("Seed complete — %d upserted, %d failed", seeded, skipped)
    logger.info("db.prompt_versions total documents: %d", count)


if __name__ == "__main__":
    main()
