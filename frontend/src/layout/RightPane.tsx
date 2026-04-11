export default function RightPane() {
  return (
    <div className="h-full bg-[#f4f4f4] border-l border-[#e0e0e0] flex flex-col overflow-hidden">
      <div className="px-3 py-3 border-b border-[#e0e0e0] flex items-center justify-between">
        <span className="text-xs font-semibold text-[#525252] uppercase tracking-wider">Agent Panel</span>
        <span className="text-[10px] text-[#a8a8a8] bg-[#e0e0e0] px-1.5 py-0.5 rounded font-mono">Packaging Agent</span>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <p className="text-xs text-[#a8a8a8] text-center px-4">
          Agent interaction — Phase 5
        </p>
      </div>
      <div className="px-3 py-3 border-t border-[#e0e0e0]">
        <div className="flex items-center gap-2 bg-white border border-[#e0e0e0] rounded px-3 py-2">
          <span className="text-xs text-[#a8a8a8] flex-1">Send a message…</span>
        </div>
      </div>
    </div>
  )
}
