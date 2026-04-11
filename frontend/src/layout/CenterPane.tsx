export default function CenterPane() {
  return (
    <div className="h-full bg-white flex flex-col overflow-hidden">
      <div className="px-4 py-3 border-b border-[#e0e0e0] flex gap-1">
        {['Onboarding', 'Loan Request', 'Documents', 'Research', 'Deck', 'Status'].map((tab) => (
          <button
            key={tab}
            className="px-3 py-1.5 text-xs font-medium text-[#525252] hover:text-[#161616] hover:bg-[#f4f4f4] rounded transition-colors first:text-[#161616] first:bg-[#f4f4f4]"
          >
            {tab}
          </button>
        ))}
      </div>
      <div className="flex-1 flex items-center justify-center">
        <p className="text-xs text-[#a8a8a8] text-center px-4">
          Tab content — Phase 3+
        </p>
      </div>
    </div>
  )
}
