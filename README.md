# Deckr

**Prepare for Capital. Powered by Watson.**

🌐 **Live demo: [deckr-ai.com](https://deckr-ai.com)**

Deckr is a **multi-agent AI workspace** for commercial borrowers preparing for a capital or debt raise.

Upload docs → Answer two forms → **10 agents. Complete package. ~5 minutes.**

A borrower runs the pipeline and gets:
- A **13-section credit memorandum** written from the lender's perspective
- An **optimized term sheet** — structured from the lender's logic, calibrated to the borrower's advantage, and built to attract competitive bids

**Built by Bankers. Powered by Watson.**

---

## Demo

![Deckr UI — Deckr tab showing optimized term sheet output](docs/demo.png)

🎬 **Full walkthrough: [YouTube Demo](https://www.youtube.com/watch?v=50bChirvvTo)**

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
| Deckr | `Deck/deckr.md` (optimized term sheet) |

All agents run through **IBM watsonx Orchestrate** (GPT-OSS 120B via AWS Bedrock).

**SLACR:** See [`frameworks/Credit_Risk_Framework.md`](frameworks/Credit_Risk_Framework.md).

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

## Acknowledgements

Built with [IBM watsonx Orchestrate](https://www.ibm.com/products/watsonx-orchestrate) and [IBM watsonx.ai](https://www.ibm.com/products/watsonx-ai).

Agent orchestration powered by the watsonx Orchestrate ADK. Language models served via AWS Bedrock (GPT-OSS 120B). Embeddings via `ibm/slate-125m-english-rtrvr-v2`.

---

## License

© 2025 Alan Greenfield. All rights reserved.

This repository is made available for review and evaluation purposes only. No part of this codebase may be reproduced, distributed, or used without explicit written permission from the author.

---

## Security

- `backend/.env` and `backend/data/` are gitignored — never committed
- All IBM API calls are backend-only — credentials never reach the frontend
- Upload allowlist enforced — `.exe` / `.sh` rejected; 50 MB max
- All cloud secrets stored in GCP Secret Manager — never in environment files on Cloud Run
- Cloud Run endpoint is publicly accessible for the demo; `ALLOWED_ORIGINS` will be restricted to known domains post-demo
