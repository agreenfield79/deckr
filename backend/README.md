# Deckr — Backend

Python 3.10.11+ · FastAPI · SQLAlchemy · Alembic

## Structure

```
backend/
├── routers/           # agent, workspace, forms, upload, tools, risk, financials,
│                      # slacr, projections, interpret, deck, deckr, graph,
│                      # mongo, status, schema
├── services/          # agent_service, agent_registry, orchestrate_client,
│                      # watsonx_client, sql_service, mongo_service, graph_service,
│                      # vector_service, embeddings_service, extraction_service,
│                      # extraction_persistence_service, projections_service,
│                      # interpret_service, slacr_service, deck_service,
│                      # enrichment_service, workspace_service, tool_service,
│                      # cos_service, db_factory, status_service, event_bus,
│                      # security, limiter, token_cache, form_serializers
├── models/            # sql_models, agent, borrower, loan, slacr,
│                      # neural_slacr_output, graph_models, tool
├── agents/            # <agent>.agent.yaml — Orchestrate ADK definitions (11 agents)
│                      # extraction, financial, industry, collateral, guarantor,
│                      # risk, interpreter, packaging, review, policy, deckr
├── prompts/           # <agent>_agent.txt — system prompts
├── knowledge_bases/   # policy_regulatory_kb — ECOA, FHA, SBA, OCC/FFIEC (policy_agent)
├── migrations/        # Alembic migrations 001–012
│                      # 001: initial schema
│                      # 002: column corrections + ENUM bootstrap
│                      # 003–011: incremental schema refinements
│                      # 012: widen financial_ratios NUMERIC columns to (20,4)
├── seed_prompt_versions.py  # Seeds prompt version history for agent prompts
├── tools_openapi.yaml # OpenAPI spec imported into IBM watsonx Orchestrate
├── Dockerfile         # Cloud Run image — uvicorn on ${PORT:-8000}
├── docker-compose.yml # Local stack: PostgreSQL :5432, MongoDB :27017, Neo4j :7474/:7687
├── main.py            # FastAPI app entrypoint
├── alembic.ini        # Alembic config
├── requirements.txt   # Python dependencies
└── .env.example       # Blank credential template — safe to commit
```

## Database Tiers

| Tier | Local | Cloud |
|---|---|---|
| SQL | SQLite (`data/deckr.db`) | Cloud SQL PostgreSQL 15 + pgvector |
| Document | MongoDB Docker `:27017` | MongoDB Atlas (`deckr-cloud`) |
| Graph | Neo4j Docker `:7687` / NetworkX fallback | Neo4j AuraDB |
| Vector | ChromaDB (local) | pgvector (PostgreSQL) |

Controlled by `STORAGE_BACKEND=local|cloud` in `.env`.

## Pipeline Stages

```
Extraction → [Financial ‖ Industry ‖ Collateral ‖ Guarantor] → Risk → Interpreter → Packaging → Review → Policy → Deckr
```

All 11 agents run through IBM watsonx Orchestrate (GPT-OSS 120B). Agent configs in `agents/`, system prompts in `prompts/`. The Policy Agent uses a vector-indexed regulatory knowledge base (`knowledge_bases/`) for fair-lending governance review.

## Local Setup

**Prerequisites:** Python 3.10.11+ · Docker Desktop (optional) · IBM Cloud account with watsonx.ai + Orchestrate access · ngrok account with a configured static domain

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env       # fill in credentials
alembic upgrade head
uvicorn main:app --reload --port 8000
```

### Optional: Full Docker Stack

```powershell
docker-compose -f backend/docker-compose.yml up -d
# PostgreSQL :5432 · MongoDB :27017 · Neo4j :7474/:7687
```

Without Docker the backend defaults to SQLite + NetworkX in-memory. MongoDB still requires a connection.

### ngrok (local backend with cloud Orchestrate)

ngrok exposes the local backend to IBM watsonx Orchestrate so agent tool calls can reach `localhost:8000` from IBM's cloud.

```powershell
ngrok http --domain=<your-ngrok-static-domain> 8000
```

Set `NGROK_DOMAIN=https://<your-ngrok-static-domain>` in `.env`.

In the Orchestrate UI (`Tools → [toolkit] → server URL`), set the active server to match your deployment track. Only one server can be active at a time — switching is a single field edit, no re-import required.

## Environment Variables

Copy `.env.example` to `.env`:

```
# IBM Core
IBMCLOUD_API_KEY=
WATSONX_PROJECT_ID=
WATSONX_URL=              # https://us-south.ml.cloud.ibm.com
WATSONX_API_VERSION=      # 2024-05-31

# Orchestrate (one per agent)
ORCHESTRATE_BASE_URL=
ORCHESTRATE_API_KEY=
ORCHESTRATE_AGENT_ID_EXTRACTION=
ORCHESTRATE_AGENT_ID_FINANCIAL=
ORCHESTRATE_AGENT_ID_INDUSTRY=
ORCHESTRATE_AGENT_ID_COLLATERAL=
ORCHESTRATE_AGENT_ID_GUARANTOR=
ORCHESTRATE_AGENT_ID_RISK=
ORCHESTRATE_AGENT_ID_INTERPRETER=
ORCHESTRATE_AGENT_ID_PACKAGING=
ORCHESTRATE_AGENT_ID_REVIEW=
ORCHESTRATE_AGENT_ID_POLICY=
ORCHESTRATE_AGENT_ID_DECKR=

# Databases
DB_URL=                   # sqlite:///./data/deckr.db  or  postgresql+psycopg2://...
MONGO_URL=                # mongodb://localhost:27017
MONGO_DB_NAME=            # deckr
NEO4J_URL=                # bolt://localhost:7687
NEO4J_USER=               # neo4j
NEO4J_PASSWORD=           # SENSITIVE — set in .env only, never commit
FIRESTORE_PROJECT_ID=     # GCP project ID (optional — Firestore feature flag)

# Storage & Routing
STORAGE_BACKEND=          # local | cloud
COS_API_KEY=
COS_BUCKET_NAME=          # deckr-workspace
WORKSPACE_ROOT=

# Server
ALLOWED_ORIGINS=          # http://localhost:5173 (local) or your Vercel domain
LOG_LEVEL=                # INFO | DEBUG

# External
SERPAPI_KEY=
NGROK_DOMAIN=
```

Frontend env vars (`VITE_*`) are configured in `frontend/.env.local` (local) or the Vercel dashboard (cloud). See `frontend/README.md`.

## Feature Flags

Boolean strings — defaults shown:

| Flag | Default | Purpose |
|---|---|---|
| `ENABLE_EXTRACTION` | `true` | 3-pass PDF extraction |
| `USE_ORCHESTRATE` | `true` | Route agents through Orchestrate |
| `ENABLE_EMBEDDINGS` | `true` | Semantic retrieval for agent context |
| `USE_COS` | `false` | IBM COS for file I/O |
| `ENABLE_WDU` | `false` | watsonx Document Understanding (pending) |
| `MULTI_DEAL_MODE` | `false` | Per-deal filesystem isolation |


