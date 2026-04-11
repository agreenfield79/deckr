import logging
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# --- Logging setup ---
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="[%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("deckr")

# Fail fast — backend is non-functional without IBM credentials
if not os.getenv("IBMCLOUD_API_KEY"):
    logger.error("IBMCLOUD_API_KEY is not set. Add it to backend/.env before starting.")
    sys.exit(1)

from routers import agent, workspace, forms, upload, deck, status, risk

# --- Credential keys — presence only, never values ---
_CREDENTIAL_KEYS = {"IBMCLOUD_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_URL", "WATSONX_API_VERSION"}
_FLAG_KEYS       = {"USE_ORCHESTRATE", "ENABLE_EXTRACTION"}
_PATH_KEYS       = {"WORKSPACE_ROOT"}


def _config_status() -> dict:
    result = {}
    for key in sorted(_CREDENTIAL_KEYS):
        result[key] = "set" if os.getenv(key) else "missing"
    for key in sorted(_FLAG_KEYS):
        result[key] = os.getenv(key, "false")
    for key in sorted(_PATH_KEYS):
        result[key] = os.getenv(key, "(not set)")
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Deckr API starting up")
    for key in sorted(_CREDENTIAL_KEYS):
        val = os.getenv(key)
        logger.info("  %-28s %s", key, "✓ set" if val else "✗ MISSING")
    for key in sorted(_FLAG_KEYS):
        logger.info("  %-28s %s", key, os.getenv(key, "false"))
    logger.info("  %-28s %s", "WORKSPACE_ROOT", os.getenv("WORKSPACE_ROOT", "(not set)"))
    logger.info("Deckr API ready — http://localhost:8000/api/health")
    yield
    logger.info("Deckr API shutting down")


app = FastAPI(title="Deckr API", version="0.1.0", lifespan=lifespan)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent.router,     prefix="/api/agent",     tags=["agent"])
app.include_router(workspace.router, prefix="/api/workspace", tags=["workspace"])
app.include_router(forms.router,     prefix="/api/forms",     tags=["forms"])
app.include_router(upload.router,    prefix="/api/upload",    tags=["upload"])
app.include_router(deck.router,      prefix="/api/deck",      tags=["deck"])
app.include_router(status.router,    prefix="/api/status",    tags=["status"])
app.include_router(risk.router,      prefix="/api/risk",      tags=["risk"])


@app.get("/api/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "config": _config_status(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
