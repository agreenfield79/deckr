import { ChevronRight } from 'lucide-react'
import AgentPanel from '../agents/AgentPanel'

interface RightPaneProps {
  onCollapse: () => void
}

export default function RightPane({ onCollapse }: RightPaneProps) {
  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Slim collapse bar at the top of the right pane */}
      <div className="shrink-0 flex items-center justify-start px-2 py-1 bg-[#f4f4f4] border-b border-[#e0e0e0]">
        <button
          onClick={onCollapse}
          title="Collapse agent panel"
          className="p-1 text-[#8d8d8d] hover:text-[#161616] hover:bg-[#e0e0e0] rounded transition-colors"
        >
          <ChevronRight size={13} />
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        <AgentPanel />
      </div>
    </div>
  )
}
