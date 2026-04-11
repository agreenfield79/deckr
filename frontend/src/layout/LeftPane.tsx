import WorkspaceExplorer from '../explorer/WorkspaceExplorer'

export default function LeftPane() {
  return (
    <div className="h-full bg-[#f4f4f4] flex flex-col overflow-hidden">
      <div className="px-3 py-2.5 border-b border-[#e0e0e0] shrink-0">
        <span className="text-xs font-semibold text-[#525252] uppercase tracking-wider">
          Workspace
        </span>
      </div>
      <div className="flex-1 min-h-0">
        <WorkspaceExplorer />
      </div>
    </div>
  )
}
