import { ChevronLeft } from 'lucide-react'
import WorkspaceExplorer from '../explorer/WorkspaceExplorer'

interface LeftPaneProps {
  onCollapse: () => void
}

export default function LeftPane({ onCollapse }: LeftPaneProps) {
  return (
    <div className="h-full bg-[#f4f4f4] flex flex-col overflow-hidden">
      <div className="px-3 py-2.5 border-b border-[#e0e0e0] shrink-0 flex items-center justify-between">
        <span className="text-xs font-semibold text-[#525252] uppercase tracking-wider">
          Workspace
        </span>
        <button
          onClick={onCollapse}
          title="Collapse workspace"
          className="p-1 text-[#8d8d8d] hover:text-[#161616] hover:bg-[#e0e0e0] rounded transition-colors"
        >
          <ChevronLeft size={13} />
        </button>
      </div>
      <div className="flex-1 min-h-0">
        <WorkspaceExplorer />
      </div>
    </div>
  )
}
