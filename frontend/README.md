# Deckr — Frontend

React 19 · TypeScript · Vite · Tailwind CSS v4

Three-pane workspace UI: file explorer (left), tabbed content (center), agent control panel (right).

## Stack

| | |
|---|---|
| Framework | React 19 + TypeScript + Vite |
| Styling | Tailwind CSS v4 |
| Charts | `@carbon/charts-react`, D3, `@visx/*`, Cytoscape.js |
| Markdown | `react-markdown` + `remark-gfm` |
| Layout | `react-resizable-panels` |
| Icons | `lucide-react` |

## Structure

```
src/
├── agents/        # AgentPanel, AgentOffice, AgentSelector, AgentWordCloud,
│                  # useAgent.ts, useAgentEvents.ts, AgentActions, AgentMessage
├── api/           # client.ts, agent.ts, upload.ts, financials.ts, workspace.ts,
│                  # health.ts, forms.ts, deck.ts, deckr.ts, interpret.ts,
│                  # pipelineRuns.ts, projections.ts, slacr.ts, status.ts, admin.ts
├── charts/        # FinancialCharts.tsx, ProjectionsChart.tsx
├── components/    # DealGraph, ExternalNetworkGraph, RiskConcentrationGraph,
│                  # FinancialSummaryGrid, PipelineGantt, RiskScoreGauge,
│                  # LimeExplanationChart, DocumentCoverageHeatmap,
│                  # DeckrPoster, GraphNodeDrawer, StorageBadge, DevModePanel
├── context/       # ApiContext, ConfigContext, ProjectContext, ToastContext
├── editor/        # MarkdownEditor, MarkdownViewer
├── explorer/      # WorkspaceExplorer, FileTreeNode, ContextMenu, useWorkspace.ts
├── forms/         # BorrowerForm, LoanForm, FormField
├── hooks/         # useStatus, useSession, useProject, useSlacrScore
├── layout/        # AppShell, LeftPane, CenterPane, RightPane
├── risk/          # SlacrWorksheet, useSlacrScore
├── tabs/          # OnboardingTab, LoanRequestTab, DocumentsTab, ResearchTab,
│                  # DeckTab, DeckrTab, ProposalTab, FinalTab, StatusTab,
│                  # InterpretTab, SlacrWorksheet, TabBar
└── types/         # agent.ts, forms.ts, slacr.ts, workspace.ts
```

## Key Notes

- `api/client.ts` — all API calls prepend `_baseUrl` from `VITE_API_BASE_URL`; `upload.ts` and `agent.ts` use `getApiBaseUrl()` directly for multipart/streaming requests
- `useAgentEvents.ts` — SSE connection uses `VITE_SSE_BASE_URL || 'http://localhost:8000'` (uses `||` not `??` — intentional, handles empty string from `.env.production`)
- Build script uses `vite build` only (no `tsc -b`) — esbuild transpiles without type-check pass
- `.npmrc` sets `legacy-peer-deps=true` for React 19 / `@visx` peer compatibility

## Local Dev

```powershell
npm install
npm run dev     # http://localhost:5173
```

## Production Build

```powershell
npm run build   # outputs to dist/
```

Set `VITE_API_BASE_URL` and `VITE_SSE_BASE_URL` in `.env.local`.
