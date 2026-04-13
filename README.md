# Deckr

**Prepare for Capital. Powered by Watson.**

Deckr is a borrower-facing, multi-agent AI workspace that helps SMB owners and CFOs assemble lender-ready commercial underwriting packages. It combines structured intake, document organization, AI-assisted analysis, and a generated financing deck — designed to feel like a modern executive workspace, not a chatbot.

---

## What It Does

A borrower opens Deckr, uploads financial materials, and works with a set of specialized AI agents that collaborate to build a complete underwriting package:

- **Packaging Agent** — assembles the lender-ready deck
- **Financial Analysis Agent** — analyzes statements, computes ratios, identifies trends
- **Risk Scoring Agent** — scores credit risk, explains drivers, suggests mitigants
- **Coordination Agent** *(planned)* — tracks missing materials, manages checklist
- **Review Agent** *(planned)* — validates narrative consistency and completeness

Agents read and write shared workspace files. The workspace is the memory.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript + Vite + Tailwind CSS |
| Backend | FastAPI (Python) |
| AI | IBM watsonx.ai — Granite, Llama 70B, Mistral |
| Storage | Local filesystem (MVP) → IBM Cloud Object Storage (post-MVP) |
| Orchestration | IBM watsonx Orchestrate via ADK (Phase 12) |

---

## Project Structure

```
deckr/
├── frontend/          # React app — three-pane workspace UI
├── backend/           # FastAPI — agent router, watsonx client, workspace service
├── frameworks/        # Credit_Risk_Framework.md — SLACR source of truth
├── .gitignore
└── README.md
```

> Planning documents (architecture outline, implementation plan, product brief) are in a local `admin/` folder excluded from version control.

---

## Local Development

### Prerequisites

- Node.js 18+
- Python 3.11+
- An IBM Cloud account with watsonx.ai access
- An IBM Cloud API key with watsonx project permissions

### Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# Fill in your IBM credentials in .env
uvicorn main:app --reload
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

The app runs at `http://localhost:5173`. The Vite dev server proxies all `/api/*` calls to `http://localhost:8000`.

### ngrok (required for Orchestrate tool calls)

IBM watsonx Orchestrate calls tool endpoints over a public HTTPS URL. Use ngrok to expose the local backend during development.

```powershell
# Start the backend first, then in a separate terminal:
ngrok http 8000 --domain=<your-static-domain>.ngrok-free.dev
```

Verify the tunnel is up:

```powershell
Invoke-RestMethod -Uri "https://<your-static-domain>.ngrok-free.dev/api/health" `
  -Headers @{ "ngrok-skip-browser-warning" = "true" }
```

- The static domain is set in `backend/tools_openapi.yaml` under `servers.url`
- ngrok must be running whenever Orchestrate agents invoke tools
- Keep backend → ngrok → Orchestrate in that start order

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in your values:

```
IBMCLOUD_API_KEY=        # IBM Cloud API key — never commit this
WATSONX_PROJECT_ID=      # watsonx.ai project ID
WATSONX_URL=             # e.g. https://us-south.ml.cloud.ibm.com
WATSONX_API_VERSION=     # 2024-05-31
WORKSPACE_ROOT=          # path to local workspace folder
```

The backend generates IAM tokens from your API key at runtime. Credentials never reach the frontend.

---

## Security

- `backend/.env` is gitignored — never committed
- `backend/workspace_root/` is gitignored — borrower data stays local
- All IBM API calls are backend-only
- All workspace file paths are validated against `WORKSPACE_ROOT` to prevent directory traversal

---

## Status

Currently in active development — Phase 0 (repository setup) complete.

See `admin/Implementation_Plan.md` for the full 11-phase build sequence.
