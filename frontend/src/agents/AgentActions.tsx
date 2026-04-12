import { Loader2, Play, Zap } from 'lucide-react'
import type { AgentInfo, PipelineStepState } from '../types/agent'

const STUB_AGENTS = ['coordination', 'review']
const AGENT_LABELS: Record<string, string> = {
  packaging: 'Full Package',
  financial: 'Financial',
  risk:      'SLACR Risk',
  coordination: 'Coordination',
  review:    'Review',
}
const AGENT_TOOLTIPS: Record<string, string> = {
  packaging:    'Runs all financial and risk agents then assembles the full credit package',
  financial:    'Analyzes uploaded financials — leverage, liquidity, collateral, and guarantor',
  risk:         'Scores the deal using the SLACR framework and writes a risk narrative',
  coordination: 'Coordinates multi-agent workflows — coming soon',
  review:       'Performs a final compliance review of the complete package — coming soon',
}

const STEP_STATUS_ICONS: Record<PipelineStepState['status'], string> = {
  pending:  '○',
  running:  '◌',
  done:     '●',
  error:    '✕',
}

interface AgentActionsProps {
  agents: AgentInfo[]
  runningAgent: string | null
  onRun: (agentName: string) => void
  isPipelineRunning?: boolean
  pipelineSteps?: PipelineStepState[]
  onRunPipeline?: () => void
}

export default function AgentActions({
  agents,
  runningAgent,
  onRun,
  isPipelineRunning = false,
  pipelineSteps = [],
  onRunPipeline,
}: AgentActionsProps) {
  if (agents.length === 0) return null

  const isAnyBusy = !!runningAgent || isPipelineRunning

  return (
    <div className="px-3 py-2 border-t border-[#e0e0e0]">
      <p className="text-[10px] text-[#8d8d8d] mb-1.5 font-semibold uppercase tracking-wider">
        Quick Run
      </p>

      {/* Run Full Analysis — pipeline button */}
      {onRunPipeline && (
        <button
          onClick={onRunPipeline}
          disabled={isAnyBusy}
          title="Run Financial → SLACR Risk → Packaging → Review in sequence"
          className={`w-full flex items-center justify-center gap-1.5 px-2 py-1.5 mb-1.5 text-xs font-semibold rounded transition-colors
            ${
              isPipelineRunning
                ? 'text-white bg-[#6929c4] border border-[#6929c4]'
                : 'text-[#6929c4] bg-white border border-[#d4bbff] hover:bg-[#f6f2ff] hover:border-[#6929c4] disabled:opacity-50 disabled:cursor-not-allowed'
            }`}
        >
          {isPipelineRunning ? (
            <Loader2 size={11} className="shrink-0 animate-spin" />
          ) : (
            <Zap size={11} className="shrink-0" />
          )}
          <span>{isPipelineRunning ? 'Running pipeline…' : 'Run Full Analysis'}</span>
        </button>
      )}

      {/* Per-step pipeline progress strip */}
      {pipelineSteps.length > 0 && (
        <div className="flex gap-1 mb-1.5">
          {pipelineSteps.map((s) => (
            <div
              key={s.agent}
              title={`${s.display_name}: ${s.status}${s.elapsed_ms ? ` (${(s.elapsed_ms / 1000).toFixed(1)}s)` : ''}`}
              className={`flex-1 flex flex-col items-center py-0.5 rounded text-[9px] font-mono transition-colors
                ${s.status === 'done'    ? 'bg-[#defbe6] text-[#198038]' : ''}
                ${s.status === 'running' ? 'bg-[#edf4ff] text-[#0f62fe]' : ''}
                ${s.status === 'error'   ? 'bg-[#fff1f1] text-[#da1e28]' : ''}
                ${s.status === 'pending' ? 'bg-[#f4f4f4] text-[#a8a8a8]' : ''}
              `}
            >
              <span className={s.status === 'running' ? 'animate-pulse' : ''}>
                {STEP_STATUS_ICONS[s.status]}
              </span>
              <span className="truncate w-full text-center" style={{ fontSize: '8px' }}>
                {s.display_name.split(' ')[0]}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Individual agent run buttons */}
      <div className="grid grid-cols-2 gap-1">
        {agents.map((agent) => {
          const isStub = STUB_AGENTS.includes(agent.name)
          const isRunning = runningAgent === agent.name
          const label = AGENT_LABELS[agent.name] ?? agent.display_name

          return (
            <button
              key={agent.name}
              onClick={() => !isStub && onRun(agent.name)}
              disabled={isStub || isAnyBusy}
              title={
                isStub
                  ? `${agent.display_name} — Coming soon`
                  : AGENT_TOOLTIPS[agent.name] ?? `Run ${agent.display_name}`
              }
              className={`flex items-center gap-1 px-2 py-1.5 text-xs rounded transition-colors truncate
                ${
                  isStub
                    ? 'text-[#a8a8a8] bg-[#f4f4f4] border border-[#e0e0e0] cursor-not-allowed'
                    : isRunning
                    ? 'text-white bg-[#0f62fe] border border-[#0f62fe]'
                    : 'text-[#0f62fe] bg-white border border-[#c6c6c6] hover:bg-[#edf4ff] hover:border-[#0f62fe] disabled:opacity-50 disabled:cursor-not-allowed'
                }`}
            >
              {isRunning ? (
                <Loader2 size={11} className="shrink-0 animate-spin" />
              ) : (
                <Play size={11} className="shrink-0" />
              )}
              <span className="truncate">{label}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
