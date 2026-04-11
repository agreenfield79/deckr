import { useEffect, useState, useCallback } from 'react'
import { Group, Panel, Separator, usePanelRef } from 'react-resizable-panels'
import { ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react'
import LeftPane from './LeftPane'
import CenterPane from './CenterPane'
import RightPane from './RightPane'
import { getHealth } from '../api/health'

const LAYOUT_KEY = 'deckr:pane-layout'
const DEFAULT_LAYOUT: [number, number, number] = [18, 55, 27]

function loadSavedLayout(): [number, number, number] {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as unknown
      if (
        Array.isArray(parsed) &&
        parsed.length === 3 &&
        parsed.every((n) => typeof n === 'number')
      ) {
        return parsed as [number, number, number]
      }
    }
  } catch {
    // ignore
  }
  return DEFAULT_LAYOUT
}

export default function AppShell() {
  const [backendOffline, setBackendOffline] = useState(false)
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const [savedLayout] = useState<[number, number, number]>(loadSavedLayout)

  const leftPanelRef = usePanelRef()
  const rightPanelRef = usePanelRef()

  // Health check on mount
  useEffect(() => {
    getHealth()
      .then(() => setBackendOffline(false))
      .catch(() => setBackendOffline(true))
  }, [])

  const handleLayoutChanged = useCallback((layout: number[]) => {
    try {
      localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout))
    } catch {
      // ignore storage errors
    }
  }, [])

  const toggleLeft = useCallback(() => {
    if (leftCollapsed) {
      leftPanelRef.current?.expand()
      setLeftCollapsed(false)
    } else {
      leftPanelRef.current?.collapse()
      setLeftCollapsed(true)
    }
  }, [leftCollapsed, leftPanelRef])

  const toggleRight = useCallback(() => {
    if (rightCollapsed) {
      rightPanelRef.current?.expand()
      setRightCollapsed(false)
    } else {
      rightPanelRef.current?.collapse()
      setRightCollapsed(true)
    }
  }, [rightCollapsed, rightPanelRef])

  return (
    <div className="flex flex-col h-screen bg-[#f4f4f4] overflow-hidden">
      <Header />

      {/* Backend offline banner */}
      {backendOffline && (
        <div className="shrink-0 flex items-center gap-2 px-4 py-2 bg-[#fff1f1] border-b border-[#ffb3b8] text-xs text-[#da1e28]">
          <AlertCircle size={13} className="shrink-0" />
          <span>
            Backend offline — start the FastAPI server with{' '}
            <code className="font-mono bg-[#ffe0e0] px-1 rounded">python main.py</code>
          </span>
          <button
            className="ml-auto underline hover:no-underline"
            onClick={() =>
              getHealth()
                .then(() => setBackendOffline(false))
                .catch(() => {})
            }
          >
            Retry
          </button>
        </div>
      )}

      <div className="flex-1 min-h-0 relative">
        <Group
          orientation="horizontal"
          className="h-full"
          defaultLayout={savedLayout}
          onLayoutChanged={handleLayoutChanged}
        >
          {/* Left pane */}
          <Panel
            id="left"
            panelRef={leftPanelRef}
            defaultSize={savedLayout[0]}
            minSize={14}
            collapsible
            collapsedSize={0}
            className="min-w-0"
          >
            <LeftPane onCollapse={toggleLeft} />
          </Panel>

          <Separator className="w-px bg-[#e0e0e0] hover:bg-[#0f62fe] transition-colors duration-150 cursor-col-resize" />

          {/* Center pane */}
          <Panel id="center" defaultSize={savedLayout[1]} minSize={32} className="min-w-0">
            <CenterPane />
          </Panel>

          <Separator className="w-px bg-[#e0e0e0] hover:bg-[#0f62fe] transition-colors duration-150 cursor-col-resize" />

          {/* Right pane */}
          <Panel
            id="right"
            panelRef={rightPanelRef}
            defaultSize={savedLayout[2]}
            minSize={20}
            collapsible
            collapsedSize={0}
            className="min-w-0"
          >
            <RightPane onCollapse={toggleRight} />
          </Panel>
        </Group>

        {/* Collapsed left strip */}
        {leftCollapsed && (
          <div className="absolute left-0 top-0 h-full w-7 bg-[#e8e8e8] border-r border-[#c6c6c6] flex items-center justify-center z-10 select-none">
            <button
              onClick={toggleLeft}
              title="Expand workspace"
              className="p-1 text-[#525252] hover:text-[#161616] hover:bg-[#d8d8d8] rounded transition-colors"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        )}

        {/* Collapsed right strip */}
        {rightCollapsed && (
          <div className="absolute right-0 top-0 h-full w-7 bg-[#e8e8e8] border-l border-[#c6c6c6] flex items-center justify-center z-10 select-none">
            <button
              onClick={toggleRight}
              title="Expand agent panel"
              className="p-1 text-[#525252] hover:text-[#161616] hover:bg-[#d8d8d8] rounded transition-colors"
            >
              <ChevronLeft size={14} />
            </button>
          </div>
        )}
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
        <span className="text-[#525252] text-xs hidden sm:block">
          Prepare for Capital. Powered by Watson.
        </span>
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
    <svg
      width="22"
      height="22"
      viewBox="0 0 22 22"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect x="2" y="2" width="18" height="18" rx="2" fill="#0f62fe" />
      <rect x="5" y="6" width="12" height="1.8" rx="0.9" fill="white" />
      <rect x="5" y="10" width="9" height="1.8" rx="0.9" fill="white" />
      <rect x="5" y="14" width="7" height="1.8" rx="0.9" fill="white" />
    </svg>
  )
}
