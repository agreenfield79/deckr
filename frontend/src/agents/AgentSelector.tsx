import type { AgentInfo, AgentName } from '../types/agent'

const STUB_AGENTS: AgentName[] = ['coordination', 'review']

interface AgentSelectorProps {
  agents: AgentInfo[]
  selected: AgentName
  onSelect: (name: AgentName) => void
}

export default function AgentSelector({ agents, selected, onSelect }: AgentSelectorProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 border-b border-[#e0e0e0] bg-[#f4f4f4]">
      <label
        htmlFor="agent-select"
        className="text-[10px] font-semibold text-[#525252] uppercase tracking-wider shrink-0"
      >
        Agent
      </label>
      <select
        id="agent-select"
        className="flex-1 text-xs text-[#161616] bg-white border border-[#c6c6c6] rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-[#0f62fe]"
        value={selected}
        onChange={(e) => onSelect(e.target.value as AgentName)}
      >
        <option value="packaging" title="Full orchestration activates in Phase 12">
          Deckr (auto)
        </option>
        {agents
          .filter((a) => a.name !== 'packaging')
          .map((agent) => (
            <option
              key={agent.name}
              value={agent.name}
              disabled={STUB_AGENTS.includes(agent.name)}
            >
              {agent.display_name}
              {STUB_AGENTS.includes(agent.name) ? ' — Coming soon' : ''}
            </option>
          ))}
      </select>
    </div>
  )
}
