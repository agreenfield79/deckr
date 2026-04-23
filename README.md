# Deckr

**Prepare for Capital. Powered by Watson.**

Deckr is a multi-agent AI workspace that automates the preparation of commercial underwriting packages at the start of a capital or debt raise. 

A borrower uploads their financial documents, answers two structured intake forms, and Deckr's 10-agent AI pipeline produces a complete credit memorandum and a deal sheet structured for capital markets in a single automated run.

The pipeline is designed not just to document the deal, but to generate an attractive structure on behalf of commercial borrowers. The Packaging Agent first constructs the full 13-section credit memorandum. The Deckr Agent then consumes that output — seeing the deal the way a bank credit officer would — before structuring the ask. This sequencing surfaces covenant positions, collateral coverage, and risk mitigants in a form calibrated to invite competitive term sheets.

---

## Agent Pipeline

```
Extraction → [Financial ‖ Industry ‖ Collateral ‖ Guarantor] → Risk → Interpreter → Packaging → Review → Deckr
```

| Agent | Output |
|-------|--------|
| Financial Data Extraction | `Financials/extracted_data.json`, `financial_data_summary.md` |
| Financial Analysis | `Agent Notes/financial_analysis.md`, `financial_ratios.json` |
| Industry Analysis | `Agent Notes/industry_analysis.md` |
| Collateral | `Agent Notes/collateral_analysis.md` |
| Guarantor | `Agent Notes/guarantor_analysis.md` |
| SLACR Risk | `SLACR/slacr_analysis.md`, `slacr.json` |
| Interpreter | `Agent Notes/neural_slacr.md` |
| Packaging | `Deck/deck.md` (13-section credit memo) |
| Review | `Agent Notes/review_notes.md` |
| Deckr | `Deck/deckr.md` (borrower-facing deal sheet) |

All agents run through **IBM watsonx Orchestrate** (GPT-OSS 120B via AWS Bedrock). Direct-path fallback: `ibm/granite-3-8b-instruct` / `meta-llama/llama-3-3-70b-instruct`.

**SLACR:** `(S×0.20) + (L×0.20) + (A×0.25) + (C×0.15) + (R×0.20)` — 1 (Low) → 5 (Decline)

---

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 · `@carbon/charts-react` · Cytoscape.js |
| Backend | Python 3.10.11+ · FastAPI · SQLAlchemy · Alembic · chromadb · tenacity |
| AI | IBM watsonx.ai — GPT-OSS-120B · `ibm/slate-125m-english-rtrvr-v2` (embeddings) |
| Orchestration | IBM watsonx Orchestrate via ADK — 10 agents, 14 tool handlers |
| SQL | SQLite (local) → Cloud SQL PostgreSQL 15 + pgvector (cloud) — 30 tables, 7 views |
| Document Store | MongoDB Docker (local) → GCP Firestore (cloud) — 14 collections |
| Graph | Neo4j Docker / NetworkX fallback (local) → AuraDB (cloud) — Layers 5A/5B active |
| Vectors | ChromaDB (local) → pgvector (cloud) — document chunk RAG |
| Storage | IBM Cloud Object Storage — bucket `deckr-workspace`, region `us-south` |
| Tunnel | ngrok static domain — exposes local backend to Orchestrate tool callbacks |

---

## Project Structure

```
borrower-underwriting-workspace/
├── frontend/              # React 19 — three-pane workspace UI
│   └── src/
│       ├── tabs/          # OnboardingTab, LoanRequestTab, DocumentsTab,
│       │                  # ResearchTab, DeckTab, StatusTab, FinalTab
│       ├── agents/        # AgentOffice.tsx, AgentWordCloud
│       └── charts/        # FinancialCharts.tsx (Revenue/EBITDA, Leverage, SLACR Radar)
├── backend/
│   ├── routers/           # agent, workspace, forms, upload, tools, risk, financials, ...
│   ├── services/          # sql_service, mongo_service, graph_service, vector_service, ...
│   ├── agents/            # <agent>.agent.yaml — Orchestrate ADK definitions
│   ├── prompts/           # <agent>_agent.txt — system prompts
│   ├── migrations/        # Alembic 001–011
│   └── tools_openapi.yaml # OpenAPI spec imported into Orchestrate
├── frameworks/            # Credit_Risk_Framework.md — SLACR source of truth
├── admin/                 # Planning docs (implementation plan, DB schemas, deployment)
├── README.md
├── README_NEW.md          # Full technical reference (~700 lines)
└── README_NEW_CONSOLIDATED.md   # This file
```

---

## Local Development

### Prerequisites

- Python 3.10.11+ · Node.js 18+ · Docker Desktop (optional)
- IBM Cloud account with watsonx.ai + Orchestrate access
- ngrok account with a configured static domain

### Quick Start

```powershell
# Backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env       # fill in credentials
alembic upgrade head
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                # http://localhost:5173
```

### Optional: Full Docker Stack

```powershell
docker-compose -f backend/docker-compose.yml up -d
# PostgreSQL :5432 · MongoDB :27017 · Neo4j :7474/:7687
```

Without Docker the backend defaults to SQLite + NetworkX in-memory. MongoDB still requires a connection.

### ngrok (required for Orchestrate tool callbacks)

```powershell
ngrok http --domain=dissuade-freckles-cornea.ngrok-free.dev 8000
```

Set `NGROK_DOMAIN=https://dissuade-freckles-cornea.ngrok-free.dev` in `backend/.env`.

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env`:

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
ORCHESTRATE_AGENT_ID_DECKR=

# Databases
DB_URL=                   # sqlite:///./data/deckr.db  or  postgresql+psycopg2://...
MONGO_URL=                # mongodb://localhost:27017
NEO4J_URL=                # bolt://localhost:7687

# Storage & Routing
STORAGE_BACKEND=          # local | cloud
COS_API_KEY=
COS_BUCKET_NAME=          # deckr-workspace
WORKSPACE_ROOT=

# External
SERPAPI_KEY=
NGROK_DOMAIN=

# Frontend (baked at build time)
VITE_API_BASE_URL=        # http://localhost:8000
```

**Feature flags** (boolean strings — defaults shown):

| Flag | Default | Purpose |
|------|---------|---------|
| `ENABLE_EXTRACTION` | `true` | 3-pass PDF extraction |
| `USE_ORCHESTRATE` | `true` | Route agents through Orchestrate |
| `ENABLE_EMBEDDINGS` | `true` | Semantic retrieval for agent context |
| `USE_COS` | `false` | IBM COS for file I/O |
| `ENABLE_WDU` | `false` | watsonx Document Understanding (pending) |
| `MULTI_TENANT` | `false` | Per-deal filesystem isolation (cloud demo) |

---

## Security

- `backend/.env` and `backend/data/` are gitignored — never committed
- All IBM API calls are backend-only — credentials never reach the frontend
- Workspace paths validated against `WORKSPACE_ROOT` (HTTP 403 on escape)
- Upload allowlist enforced — `.exe` / `.sh` rejected; 50 MB max
- Rate limiting: 5/min agent · 2/min pipeline · 3/min export

---

## Status

Full 10-agent pipeline is running end-to-end and demo-ready. Auth (A-10) is the hard gate before any public or multi-user deployment. Track B (GCP cloud deployment) is entirely pending.

See `README_NEW.md` for the complete technical reference, or `admin/` for implementation plans, database schemas, and deployment guides.
