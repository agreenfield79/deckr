import { useState } from 'react'
import { X, Sparkles } from 'lucide-react'
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
  const { activeFile, closeFile, saveActiveFile, tree, treeLoading } = useProject()
  const [activeTab, setActiveTab] = useState<TabId>('onboarding')
  const [bannerDismissed, setBannerDismissed] = useState(false)

  const isNewUser = !treeLoading && tree.length === 0 && !bannerDismissed

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

      {/* First-run welcome banner */}
      {isNewUser && (
        <div className="shrink-0 flex items-center gap-2 px-4 py-2 bg-[#edf4ff] border-b border-[#d0e2ff] text-xs text-[#0043ce]">
          <Sparkles size={13} className="shrink-0" />
          <span>
            Welcome to Deckr! Start by filling out the{' '}
            <button
              className="underline font-semibold hover:no-underline"
              onClick={() => setActiveTab('onboarding')}
            >
              Onboarding
            </button>{' '}
            form to set up your borrower workspace.
          </span>
          <button
            className="ml-auto p-0.5 hover:bg-[#d0e2ff] rounded transition-colors"
            onClick={() => setBannerDismissed(true)}
            title="Dismiss"
          >
            <X size={12} />
          </button>
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-hidden">
        {renderTab()}
      </div>
    </div>
  )
}
