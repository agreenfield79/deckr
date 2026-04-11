import { Group, Panel, Separator } from 'react-resizable-panels'
import LeftPane from './LeftPane'
import CenterPane from './CenterPane'
import RightPane from './RightPane'

export default function AppShell() {
  return (
    <div className="flex flex-col h-screen bg-[#f4f4f4] overflow-hidden">
      <Header />
      <div className="flex-1 min-h-0">
        <Group orientation="horizontal" className="h-full">
          <Panel defaultSize={18} minSize={14} className="min-w-0">
            <LeftPane />
          </Panel>

          <Separator className="w-px bg-[#e0e0e0] hover:bg-[#0f62fe] transition-colors duration-150 cursor-col-resize" />

          <Panel defaultSize={55} minSize={32} className="min-w-0">
            <CenterPane />
          </Panel>

          <Separator className="w-px bg-[#e0e0e0] hover:bg-[#0f62fe] transition-colors duration-150 cursor-col-resize" />

          <Panel defaultSize={27} minSize={20} className="min-w-0">
            <RightPane />
          </Panel>
        </Group>
      </div>
    </div>
  )
}

function Header() {
  return (
    <header className="h-12 bg-[#161616] flex items-center justify-between px-5 shrink-0 select-none">
      <div className="flex items-center gap-3">
        <DeckrLogo />
        <span className="text-white text-sm font-semibold tracking-wide">Deckr</span>
        <span className="text-[#525252] text-xs hidden sm:block">Prepare for Capital. Powered by Watson.</span>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-[#8d8d8d] text-xs font-mono">default</span>
        <button
          className="ml-3 px-3 py-1 text-xs font-medium text-[#161616] bg-[#f4f4f4] hover:bg-white rounded transition-colors"
          title="Export deck"
        >
          Export
        </button>
      </div>
    </header>
  )
}

function DeckrLogo() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <rect x="2" y="2" width="18" height="18" rx="2" fill="#0f62fe" />
      <rect x="5" y="6" width="12" height="1.8" rx="0.9" fill="white" />
      <rect x="5" y="10" width="9" height="1.8" rx="0.9" fill="white" />
      <rect x="5" y="14" width="7" height="1.8" rx="0.9" fill="white" />
    </svg>
  )
}
