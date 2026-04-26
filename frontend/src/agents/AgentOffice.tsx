import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import type { AgentActivityState } from './useAgentEvents'
import type { PipelineStepState } from '../types/agent'

// ─── Agent metadata ────────────────────────────────────────────────────────────

interface AgentCard {
  key: string
  label: string
  abbr: string
  /** Tailwind ring/bg colour classes for the Working state */
  activeColor: string
}

// Pre-processing card — rendered full-width above the analytical grid
const EXTRACTION_CARD: AgentCard = {
  key: 'extraction', label: 'Extraction', abbr: 'Ex', activeColor: 'ring-[#d74108] bg-[#fff2e8]',
}

// Post-processing card — rendered full-width below the analytical grid
const DECKR_CARD: AgentCard = {
  key: 'deckr', label: 'Deckr', abbr: 'Dk', activeColor: 'ring-[#ff832b] bg-[#fff2e8]',
}

// Governance card — rendered full-width between the analytical grid and Deckr output
const POLICY_CARD: AgentCard = {
  key: 'policy', label: 'Policy', abbr: 'Po', activeColor: 'ring-[#6929c4] bg-[#f6f2ff]',
}

// Analytical pipeline cards — rendered in a 4-column grid (Phase 28: 8 cards).
// Row 1 (parallel analysis stage): Financial | Industry | Collateral | Guarantor
// Row 2 (sequential post-analysis): Risk | Interpreter | Packaging | Review
// Extraction (pre) and Deckr (post) are rendered as separate full-width cards.
const AGENT_CARDS: AgentCard[] = [
  { key: 'financial',    label: 'Financial',    abbr: 'F',    activeColor: 'ring-[#0f62fe] bg-[#edf4ff]' },
  { key: 'industry',     label: 'Industry',     abbr: 'In',   activeColor: 'ring-[#198038] bg-[#defbe6]' },
  { key: 'collateral',   label: 'Collateral',   abbr: 'Co',   activeColor: 'ring-[#9f1853] bg-[#fff0f7]' },
  { key: 'guarantor',    label: 'Guarantor',    abbr: 'G',    activeColor: 'ring-[#b28600] bg-[#fdf6dd]' },
  { key: 'risk',         label: 'Risk',         abbr: 'R',    activeColor: 'ring-[#6929c4] bg-[#f6f2ff]' },
  { key: 'interpreter',  label: 'Interpreter',  abbr: 'Int',  activeColor: 'ring-[#005d5d] bg-[#d9fbfb]' },
  { key: 'packaging',    label: 'Packaging',    abbr: 'P',    activeColor: 'ring-[#0043ce] bg-[#edf4ff]' },
  { key: 'review',       label: 'Review',       abbr: 'Rev',  activeColor: 'ring-[#007d79] bg-[#d9fbfb]' },
]

const LS_KEY = 'deckr:agentOfficeCollapsed'

// ─── Elapsed timer hook ────────────────────────────────────────────────────────

function useElapsedMs(since: number | undefined, active: boolean): number {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!active || since === undefined) {
      setElapsed(0)
      return
    }
    setElapsed(Date.now() - since)
    const id = setInterval(() => setElapsed(Date.now() - since), 500)
    return () => clearInterval(id)
  }, [since, active])

  return elapsed
}

// ─── Single agent status card ─────────────────────────────────────────────────

interface AgentStatusCardProps {
  card: AgentCard
  status: 'idle' | 'working' | 'saving'
  pipelineStatus?: 'pending' | 'running' | 'done' | 'error'
  since?: number
}

function AgentStatusCard({ card, status, pipelineStatus, since }: AgentStatusCardProps) {
  const isWorking = status === 'working' || pipelineStatus === 'running'
  const isSaving = status === 'saving'
  const isDone = pipelineStatus === 'done'
  const isError = pipelineStatus === 'error'

  const elapsed = useElapsedMs(since, isWorking)
  const elapsedSec = (elapsed / 1000).toFixed(1)

  // Derive display state
  let ringClasses = 'ring-transparent bg-white'
  let badgeText = ''
  let badgeClasses = ''
  let pulseRing = false

  if (isWorking) {
    ringClasses = card.activeColor
    badgeText = elapsed > 0 ? `${elapsedSec}s` : 'Working'
    badgeClasses = 'text-[#0f62fe] bg-[#d0e2ff]'
    pulseRing = true
  } else if (isSaving) {
    ringClasses = 'ring-[#198038] bg-[#defbe6]'
    badgeText = 'Saving'
    badgeClasses = 'text-[#198038] bg-[#a7f0ba]'
  } else if (isDone) {
    ringClasses = 'ring-[#24a148] bg-[#defbe6]'
    badgeText = 'Done'
    badgeClasses = 'text-[#198038] bg-[#defbe6]'
  } else if (isError) {
    ringClasses = 'ring-[#da1e28] bg-[#fff1f1]'
    badgeText = 'Error'
    badgeClasses = 'text-[#da1e28] bg-[#ffd7d9]'
  }

  return (
    <div
      className={`relative flex flex-col items-center justify-center gap-1 rounded-lg border border-[#e0e0e0] ring-2 px-2 py-2 transition-all duration-300 ${ringClasses}`}
    >
      {/* Pulse animation overlay for working state */}
      {pulseRing && (
        <span className="absolute inset-0 rounded-lg ring-2 ring-[#0f62fe] animate-ping opacity-25 pointer-events-none" />
      )}

      {/* Agent avatar */}
      <span className="text-[11px] font-bold text-[#525252] bg-[#e0e0e0] rounded-full w-6 h-6 flex items-center justify-center shrink-0 z-10">
        {card.abbr}
      </span>

      {/* Agent name */}
      <span className="text-[9px] font-semibold text-[#525252] text-center leading-tight z-10">
        {card.label}
      </span>

      {/* Status badge */}
      {badgeText ? (
        <span className={`text-[8px] font-semibold px-1 py-0.5 rounded z-10 transition-colors ${badgeClasses}`}>
          {badgeText}
        </span>
      ) : (
        <span className="text-[8px] text-[#a8a8a8] z-10">idle</span>
      )}
    </div>
  )
}

// ─── Main AgentOffice component ───────────────────────────────────────────────

interface AgentOfficeProps {
  agentActivity: AgentActivityState
  pipelineSteps: PipelineStepState[]
  isPipelineRunning: boolean
  pipelineTotalMs: number | null
}

export default function AgentOffice({ agentActivity, pipelineSteps, isPipelineRunning, pipelineTotalMs }: AgentOfficeProps) {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(LS_KEY) === 'true'
    } catch {
      return false
    }
  })

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev
      try { localStorage.setItem(LS_KEY, String(next)) } catch { /* ignore */ }
      return next
    })
  }

  // Build a pipeline step lookup by agent key for easy access
  const pipelineByAgent = useRef<Record<string, PipelineStepState>>({})
  pipelineByAgent.current = Object.fromEntries(pipelineSteps.map((s) => [s.agent, s]))

  return (
    <div className="border-b border-[#e0e0e0] shrink-0">
      {/* Section header */}
      <button
        onClick={toggleCollapsed}
        className="w-full flex items-center justify-between px-3 py-1.5 text-[10px] font-semibold text-[#525252] uppercase tracking-wider bg-[#f4f4f4] hover:bg-[#e8e8e8] transition-colors"
        title={collapsed ? 'Expand Agent Office' : 'Collapse Agent Office'}
      >
        <span>Agent Office</span>
        <span className="flex items-center gap-1">
          {isPipelineRunning && (
            <span className="text-[8px] font-semibold text-[#0f62fe] bg-[#d0e2ff] px-1 py-0.5 rounded animate-pulse">
              Pipeline
            </span>
          )}
          {!isPipelineRunning && pipelineTotalMs !== null && (() => {
            const totalSec = pipelineTotalMs / 1000
            const display = totalSec >= 60
              ? `${Math.floor(totalSec / 60)}m ${Math.round(totalSec % 60)}s`
              : `${totalSec.toFixed(0)}s`
            const hasError = pipelineSteps.some((s) => s.status === 'error')
            return (
              <span className={`text-[8px] font-semibold px-1 py-0.5 rounded ${
                hasError
                  ? 'text-[#da1e28] bg-[#ffd7d9]'
                  : 'text-[#198038] bg-[#defbe6]'
              }`}>
                {hasError ? '⚠' : '✓'} {display}
              </span>
            )
          })()}
          {collapsed ? <ChevronDown size={11} /> : <ChevronUp size={11} />}
        </span>
      </button>

      {/* Card grid */}
      {!collapsed && (
        <div className="px-2 py-2 bg-[#f9f9f9]">
          {/* Pre-processing — Extraction Agent, full-width above the analytical grid */}
          <p className="text-[8px] font-semibold text-[#8d8d8d] uppercase tracking-wider mb-1 px-0.5">
            Pre-processing
          </p>
          <div className="mb-2">
            <AgentStatusCard
              card={EXTRACTION_CARD}
              status={agentActivity[EXTRACTION_CARD.key]?.status ?? 'idle'}
              pipelineStatus={pipelineByAgent.current[EXTRACTION_CARD.key]?.status}
              since={agentActivity[EXTRACTION_CARD.key]?.since}
            />
          </div>

          {/* Analysis — 4-column grid: [Financial | Industry | Collateral | Guarantor] then [Risk | Interpreter | Packaging | Review] */}
          <p className="text-[8px] font-semibold text-[#8d8d8d] uppercase tracking-wider mb-1 px-0.5">
            Analysis
          </p>
          <div className="grid grid-cols-4 gap-1.5">
            {AGENT_CARDS.map((card) => {
              const activity = agentActivity[card.key]
              const pipelineStep = pipelineByAgent.current[card.key]
              return (
                <AgentStatusCard
                  key={card.key}
                  card={card}
                  status={activity?.status ?? 'idle'}
                  pipelineStatus={pipelineStep?.status}
                  since={activity?.since}
                />
              )
            })}
          </div>

          {/* Output — Deckr Agent, full-width below the analytical grid */}
          <p className="text-[8px] font-semibold text-[#8d8d8d] uppercase tracking-wider mt-2 mb-1 px-0.5">
            Governance
          </p>
          <div className="mb-2">
            <AgentStatusCard
              card={POLICY_CARD}
              status={agentActivity[POLICY_CARD.key]?.status ?? 'idle'}
              pipelineStatus={pipelineByAgent.current[POLICY_CARD.key]?.status}
              since={agentActivity[POLICY_CARD.key]?.since}
            />
          </div>

          {/* Output — Deckr Agent, full-width below the governance card */}
          <p className="text-[8px] font-semibold text-[#8d8d8d] uppercase tracking-wider mt-2 mb-1 px-0.5">
            Output
          </p>
          <div className="mb-1">
            <AgentStatusCard
              card={DECKR_CARD}
              status={agentActivity[DECKR_CARD.key]?.status ?? 'idle'}
              pipelineStatus={pipelineByAgent.current[DECKR_CARD.key]?.status}
              since={agentActivity[DECKR_CARD.key]?.since}
            />
          </div>

          {/* Coordination Agent — greyed out until future phase */}
          <div className="mt-1.5 flex items-center justify-center gap-2 rounded-lg border border-dashed border-[#c6c6c6] bg-white px-2 py-1.5 opacity-50">
            <span className="text-[9px] font-bold text-[#a8a8a8] bg-[#e0e0e0] rounded-full w-5 h-5 flex items-center justify-center shrink-0">
              C
            </span>
            <span className="text-[9px] text-[#a8a8a8]">Coordination Agent</span>
            <span className="text-[8px] text-[#a8a8a8] italic ml-auto">Coming Soon</span>
          </div>
        </div>
      )}
    </div>
  )
}
