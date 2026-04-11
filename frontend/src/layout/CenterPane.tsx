import { useState } from 'react'
import { X } from 'lucide-react'
import { useProject } from '../context/ProjectContext'
import MarkdownEditor from '../editor/MarkdownEditor'
import TabBar, { type TabId } from '../tabs/TabBar'
import OnboardingTab from '../tabs/OnboardingTab'
import LoanRequestTab from '../tabs/LoanRequestTab'
import DocumentsTab from '../tabs/DocumentsTab'
import ResearchTab from '../tabs/ResearchTab'
import DeckTab from '../tabs/DeckTab'
import StatusTab from '../tabs/StatusTab'

export default function CenterPane() {
  const { activeFile, closeFile, saveActiveFile } = useProject()
  const [activeTab, setActiveTab] = useState<TabId>('onboarding')

  // File viewer mode — overrides tab content
  if (activeFile) {
    return (
      <div className="h-full bg-white flex flex-col overflow-hidden">
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

  const renderTab = () => {
    switch (activeTab) {
      case 'onboarding':  return <OnboardingTab />
      case 'loan':        return <LoanRequestTab />
      case 'documents':   return <DocumentsTab />
      case 'research':    return <ResearchTab />
      case 'deck':        return <DeckTab />
      case 'status':      return <StatusTab onNavigate={setActiveTab} />
    }
  }

  return (
    <div className="h-full bg-white flex flex-col overflow-hidden">
      <TabBar active={activeTab} onChange={setActiveTab} />
      <div className="flex-1 min-h-0 overflow-hidden">
        {renderTab()}
      </div>
    </div>
  )
}
