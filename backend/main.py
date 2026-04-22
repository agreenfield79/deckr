import logging
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

load_dotenv()

# --- Logging setup ---
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="[%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("deckr")

# Suppress Neo4j schema-warning notifications (relationship types not yet created —
# expected when enrichment is disabled or no data has been written via enrichment_service).
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)

# Fail fast — backend is non-functional without IBM credentials
if not os.getenv("IBMCLOUD_API_KEY"):
    logger.error("IBMCLOUD_API_KEY is not set. Add it to backend/.env before starting.")
    sys.exit(1)

from routers import agent, workspace, forms, upload, deck, deckr, status, risk, tools, interpret
from routers import financials, graph, projections, schema, slacr, mongo

# --- Credential keys — presence only, never values ---
_CREDENTIAL_KEYS = {"IBMCLOUD_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_URL", "WATSONX_API_VERSION"}
_ORCHESTRATE_CRED_KEYS = {"ORCHESTRATE_API_KEY"}
_FLAG_KEYS       = {"USE_ORCHESTRATE", "ENABLE_EXTRACTION", "ENABLE_EMBEDDINGS", "ENABLE_WDU", "USE_COS", "SCHEMA_REFACTOR_ENABLED"}
_PATH_KEYS       = {"WORKSPACE_ROOT"}


def _config_status() -> dict:
    result = {}
    for key in sorted(_CREDENTIAL_KEYS):
        result[key] = "set" if os.getenv(key) else "missing"
    for key in sorted(_FLAG_KEYS):
        result[key] = os.getenv(key, "false")
    for key in sorted(_PATH_KEYS):
        result[key] = os.getenv(key, "(not set)")
    # Orchestrate — only surfaced when USE_ORCHESTRATE is true
    if os.getenv("USE_ORCHESTRATE", "false").lower() == "true":
        result["ORCHESTRATE_BASE_URL"] = os.getenv("ORCHESTRATE_BASE_URL", "missing")
        result["ORCHESTRATE_API_KEY"] = "set" if os.getenv("ORCHESTRATE_API_KEY") else "missing"
        from services.orchestrate_client import configured_agent_ids
        ids = configured_agent_ids()
        result["ORCHESTRATE_AGENTS_CONFIGURED"] = f"{sum(bool(v) for v in ids.values())}/{len(ids)}"
    # COS — only surfaced when USE_COS is true
    if os.getenv("USE_COS", "false").lower() == "true":
        result["COS_ENDPOINT_URL"] = os.getenv("COS_ENDPOINT_URL", "missing")
        result["COS_BUCKET_NAME"]  = os.getenv("COS_BUCKET_NAME", "missing")
        result["COS_API_KEY"]      = "set" if os.getenv("COS_API_KEY") else "missing"
        result["COS_INSTANCE_CRN"] = "set" if os.getenv("COS_INSTANCE_CRN") else "missing"
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    from services.event_bus import set_main_loop
    set_main_loop(asyncio.get_running_loop())

    # ── SQL schema init (D-2: create_all for local SQLite) ──
    try:
        from services.sql_service import init_schema as _init_sql
        _init_sql()
    except Exception as _exc:
        logger.warning("SQL schema init failed (non-fatal): %s", _exc)

    # ── Graph schema init (Neo4j constraints/indexes) ──
    try:
        from services.graph_service import init_graph_schema
        init_graph_schema()
    except Exception as _exc:
        logger.warning("Graph schema init failed (non-fatal): %s", _exc)

    logger.info("Deckr API starting up")
    for key in sorted(_CREDENTIAL_KEYS):
        val = os.getenv(key)
        logger.info("  %-28s %s", key, "✓ set" if val else "✗ MISSING")
    for key in sorted(_FLAG_KEYS):
        logger.info("  %-28s %s", key, os.getenv(key, "false"))
    logger.info("  %-28s %s", "WORKSPACE_ROOT", os.getenv("WORKSPACE_ROOT", "(not set)"))
    logger.info("  %-28s %s", "STORAGE_BACKEND", os.getenv("STORAGE_BACKEND", "local"))
    logger.info("  %-28s %s", "DB_URL", os.getenv("DB_URL", "(not set)").split("@")[-1])

    # ── DB connectivity pings (D-3: warn on failure, don't crash) ──
    try:
        from services.db_factory import ping_sql, ping_mongo, ping_neo4j
        logger.info("  %-28s %s", "SQL connected",   "✓" if ping_sql()   else "✗ (degraded)")
        logger.info("  %-28s %s", "MongoDB connected","✓" if ping_mongo() else "✗ (degraded)")
        logger.info("  %-28s %s", "Neo4j connected",  "✓" if ping_neo4j() else "✗ (degraded)")
    except Exception as _exc:
        logger.warning("DB ping block failed: %s", _exc)

    # Log Orchestrate config when active
    use_orchestrate = os.getenv("USE_ORCHESTRATE", "false").lower() == "true"
    if use_orchestrate:
        logger.info("  Orchestrate integration ACTIVE")
        logger.info("  %-28s %s", "ORCHESTRATE_BASE_URL", os.getenv("ORCHESTRATE_BASE_URL", "✗ MISSING"))
        logger.info("  %-28s %s", "ORCHESTRATE_API_KEY", "✓ set" if os.getenv("ORCHESTRATE_API_KEY") else "✗ MISSING")
        from services.orchestrate_client import configured_agent_ids
        for agent_name, is_set in configured_agent_ids().items():
            logger.info("  %-28s %s", f"  agent:{agent_name}", "✓ configured" if is_set else "✗ missing")
    logger.info("Deckr API ready — http://localhost:8000/api/health")
    # Log COS config when active
    use_cos = os.getenv("USE_COS", "false").lower() == "true"
    if use_cos:
        logger.info("  COS storage ACTIVE")
        logger.info("  %-28s %s", "COS_ENDPOINT_URL", os.getenv("COS_ENDPOINT_URL", "✗ MISSING"))
        logger.info("  %-28s %s", "COS_BUCKET_NAME",  os.getenv("COS_BUCKET_NAME", "✗ MISSING"))
        logger.info("  %-28s %s", "COS_API_KEY",      "✓ set" if os.getenv("COS_API_KEY") else "✗ MISSING")
        logger.info("  %-28s %s", "COS_INSTANCE_CRN", "✓ set" if os.getenv("COS_INSTANCE_CRN") else "✗ MISSING")
    else:
        logger.info("  COS storage INACTIVE — using local filesystem (USE_COS=false)")
    logger.info("Deckr API ready — http://localhost:8000/api/health")
    yield
    logger.info("Deckr API shutting down")


app = FastAPI(title="Deckr API", version="0.1.0", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Rate limiting (Step 30.3) — slowapi, keyed by remote IP
# Limiter instance lives in services/limiter.py to avoid circular imports.
# ---------------------------------------------------------------------------
from services.limiter import limiter  # noqa: E402 (after app creation)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent.router,       prefix="/api/agent",       tags=["agent"])
app.include_router(workspace.router,   prefix="/api/workspace",   tags=["workspace"])
app.include_router(forms.router,       prefix="/api/forms",       tags=["forms"])
app.include_router(upload.router,      prefix="/api/upload",      tags=["upload"])
app.include_router(deck.router,        prefix="/api/deck",        tags=["deck"])
app.include_router(deckr.router,       prefix="/api/deckr",       tags=["deckr"])
app.include_router(status.router,      prefix="/api/status",      tags=["status"])
app.include_router(risk.router,        prefix="/api/risk",        tags=["risk"])
app.include_router(tools.router,       prefix="/api/tools",       tags=["tools"])
app.include_router(interpret.router,   prefix="/api/interpret",   tags=["interpret"])
app.include_router(financials.router,  prefix="/api/financials",  tags=["financials"])
app.include_router(graph.router,       prefix="/api/graph",       tags=["graph"])
app.include_router(projections.router, prefix="/api/projections", tags=["projections"])
app.include_router(schema.router,      prefix="/api/schema",      tags=["schema"])
app.include_router(slacr.router,       prefix="/api/slacr",       tags=["slacr"])
app.include_router(mongo.router,       prefix="/api/mongo",       tags=["mongo"])


@app.get("/api/health", tags=["health"])
def health():
    import os as _os
    storage_status: dict = {}
    try:
        from services.db_factory import db_health
        storage_status = db_health()
    except Exception as _exc:
        storage_status = {"error": str(_exc)}

    storage_mode = _os.getenv("STORAGE_BACKEND", "local")
    return {
        "status": "ok",
        "storage_mode": storage_mode,
        "config": _config_status(),
        "storage": storage_status,
        "databases": storage_status,
        "features": {
            "pipeline_history":  storage_status.get("sql", {}).get("connected", False),
            "graph_enrichment":  storage_status.get("neo4j", {}).get("connected", False),
            "vector_search":     True,  # ChromaDB available locally without Docker
            "projections":       True,  # Phase 4B complete
            "enrichment_enabled": _os.getenv("ENRICHMENT_ENABLED", "true").lower() not in ("false", "0", "off"),
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
