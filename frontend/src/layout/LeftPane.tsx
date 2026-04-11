export default function LeftPane() {
  return (
    <div className="h-full bg-[#f4f4f4] border-r border-[#e0e0e0] flex flex-col overflow-hidden">
      <div className="px-3 py-3 border-b border-[#e0e0e0]">
        <span className="text-xs font-semibold text-[#525252] uppercase tracking-wider">Workspace</span>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <p className="text-xs text-[#a8a8a8] text-center px-4">
          File explorer — Phase 2
        </p>
      </div>
    </div>
  )
}
