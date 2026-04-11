import { Loader2, Play } from 'lucide-react'
import type { AgentInfo } from '../types/agent'

const STUB_AGENTS = ['coordination', 'review']
const AGENT_LABELS: Record<string, string> = {
  packaging: 'Full Package',
  financial: 'Financial',
  risk:      'SLACR Risk',
  coordination: 'Coordination',
  review:    'Review',
}

interface AgentActionsProps {
  agents: AgentInfo[]
  runningAgent: string | null
  onRun: (agentName: string) => void
}

export default function AgentActions({ agents, runningAgent, onRun }: AgentActionsProps) {
  if (agents.length === 0) return null

  return (
    <div className="px-3 py-2 border-t border-[#e0e0e0]">
      <p className="text-[10px] text-[#8d8d8d] mb-1.5 font-semibold uppercase tracking-wider">
        Quick Run
      </p>
      <div className="grid grid-cols-2 gap-1">
        {agents.map((agent) => {
          const isStub = STUB_AGENTS.includes(agent.name)
          const isRunning = runningAgent === agent.name
          const label = AGENT_LABELS[agent.name] ?? agent.display_name

          return (
            <button
              key={agent.name}
              onClick={() => !isStub && onRun(agent.name)}
              disabled={isStub || !!runningAgent}
              title={isStub ? `${agent.display_name} — Coming soon` : `Run ${agent.display_name}`}
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
