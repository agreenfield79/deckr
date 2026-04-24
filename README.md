# Deckr

**Prepare for Capital. Powered by Watson.**

🌐 **Live demo: [deckr-ai.com](https://deckr-ai.com)**

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

All agents run through **IBM watsonx Orchestrate** (GPT-OSS 120B via AWS Bedrock).

**SLACR:** `(S×0.20) + (L×0.20) + (A×0.25) + (C×0.15) + (R×0.20)` — 1 (Low) → 5 (Decline). See [`frameworks/Credit_Risk_Framework.md`](frameworks/Credit_Risk_Framework.md).

---

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 · `@carbon/charts-react` · Cytoscape.js |
| Backend | Python 3.10.11+ · FastAPI · SQLAlchemy · Alembic · chromadb · tenacity |
| AI | IBM watsonx.ai — GPT-OSS-120B · `ibm/slate-125m-english-rtrvr-v2` (embeddings) |
| Orchestration | IBM watsonx Orchestrate via ADK — 10 agents, 14 tool handlers |
| SQL | SQLite (local) → Cloud SQL PostgreSQL 15 + pgvector (cloud) — 30 tables, 7 views |
| Document Store | MongoDB Docker (local) → MongoDB Atlas (cloud) — 14 collections |
| Graph | Neo4j Docker / NetworkX fallback (local) → AuraDB (cloud) — Layers 5A/5B active |
| Vectors | ChromaDB (local) → pgvector (cloud) — document chunk RAG |
| Storage | IBM Cloud Object Storage — bucket `deckr-workspace`, region `us-south` |
| Tunnel | ngrok static domain — exposes local backend to Orchestrate tool callbacks |

---

## Project Structure

```
borrower-underwriting-workspace/
├── backend/       # FastAPI · SQLAlchemy · Alembic · 10 Orchestrate agents
│                  # See backend/README.md for full structure, setup, and env vars
├── frontend/      # React 19 · TypeScript · Vite · Tailwind CSS v4
│                  # See frontend/README.md for full structure and setup
├── frameworks/    # Credit_Risk_Framework.md — SLACR source of truth
├── .gitignore
└── README.md
```

---

## Setup

See **[`backend/README.md`](backend/README.md)** for backend setup, environment variables, Docker stack, and ngrok configuration.

See **[`frontend/README.md`](frontend/README.md)** for frontend setup and build instructions.

---

## Security

- `backend/.env` and `backend/data/` are gitignored — never committed
- All IBM API calls are backend-only — credentials never reach the frontend
- Upload allowlist enforced — `.exe` / `.sh` rejected; 50 MB max
- All cloud secrets stored in GCP Secret Manager — never in environment files on Cloud Run
- Cloud Run endpoint is publicly accessible for the demo; `ALLOWED_ORIGINS` will be restricted to known domains post-demo
