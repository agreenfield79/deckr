import { X } from 'lucide-react'
import { useProject } from '../context/ProjectContext'
import MarkdownEditor from '../editor/MarkdownEditor'

export default function CenterPane() {
  const { activeFile, closeFile, saveActiveFile } = useProject()

  if (activeFile) {
    return (
      <div className="h-full bg-white flex flex-col overflow-hidden">
        {/* File viewer header */}
        <div className="flex items-center px-3 py-1.5 border-b border-[#e0e0e0] bg-[#f4f4f4] shrink-0">
          <span className="text-xs text-[#525252] font-mono truncate flex-1">
            {activeFile.path}
          </span>
          <button
            className="ml-2 p-1 text-[#525252] hover:text-[#161616] hover:bg-[#e0e0e0] rounded transition-colors"
            title="Close file"
            onClick={closeFile}
          >
            <X size={13} />
          </button>
        </div>
        <div className="flex-1 min-h-0">
          <MarkdownEditor
            key={activeFile.path}
            content={activeFile.content}
            filePath={activeFile.path}
            onSave={saveActiveFile}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="h-full bg-white flex flex-col overflow-hidden">
      {/* Tab bar */}
      <div className="px-4 py-3 border-b border-[#e0e0e0] flex gap-1 shrink-0">
        {['Onboarding', 'Loan Request', 'Documents', 'Research', 'Deck', 'Status'].map(
          (tab, i) => (
            <button
              key={tab}
              className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                i === 0
                  ? 'text-[#161616] bg-[#f4f4f4]'
                  : 'text-[#525252] hover:text-[#161616] hover:bg-[#f4f4f4]'
              }`}
            >
              {tab}
            </button>
          ),
        )}
      </div>
      <div className="flex-1 flex items-center justify-center">
        <p className="text-xs text-[#a8a8a8] text-center px-4">
          Tab content — Phase 3+
        </p>
      </div>
    </div>
  )
}
