import { useState, useEffect, useCallback, useRef } from 'react'
import { FilePlus, Printer } from 'lucide-react'
import { useProject } from '../context/ProjectContext'
import MarkdownEditor from '../editor/MarkdownEditor'
import MarkdownViewer from '../editor/MarkdownViewer'
import type { TreeNode } from '../types/workspace'

const RESEARCH_FOLDERS = ['Research', 'Industry', 'Management']

function flatFiles(nodes: TreeNode[], prefix = ''): TreeNode[] {
  const results: TreeNode[] = []
  for (const node of nodes) {
    if (node.type === 'file') {
      results.push(node)
    } else if (node.children) {
      results.push(...flatFiles(node.children, node.path))
    }
  }
  return results
}

function filterResearchNodes(tree: TreeNode[]): TreeNode[] {
  return tree.filter((n) => RESEARCH_FOLDERS.includes(n.name))
}

export default function ResearchTab() {
  const { tree, refreshTree, readFile, writeFile } = useProject()
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState('')
  const [loadingFile, setLoadingFile] = useState(false)

  const noteRef = useRef<HTMLDivElement>(null)

  const handlePrintNote = () => {
    const el = noteRef.current
    if (!el || !selectedPath) return

    const clone = el.cloneNode(true) as HTMLElement
    clone.id = 'print-portal'
    document.body.appendChild(clone)

    const style = document.createElement('style')
    style.id = 'print-portal-style'
    style.textContent = `
      @media print {
        @page { size: letter portrait; margin: 0.65in 0.75in; }
        body > *:not(#print-portal) { display: none !important; }
        #print-portal {
          display: block !important;
          position: static !important;
          left: auto !important;
          width: 100% !important;
          max-width: none !important;
          margin: 0 !important;
          padding: 0 !important;
          border: none !important;
          background: white !important;
        }
        #print-portal h2, #print-portal table { break-inside: avoid; }
      }
    `
    document.head.appendChild(style)

    const cleanup = () => {
      document.body.removeChild(clone)
      document.head.removeChild(style)
      window.removeEventListener('afterprint', cleanup)
    }
    window.addEventListener('afterprint', cleanup)

    window.print()
  }

  const researchNodes = filterResearchNodes(tree)
  const allFiles = flatFiles(researchNodes)

  // Open a file inline in this tab
  const openFile = useCallback(
    async (path: string) => {
      setLoadingFile(true)
      try {
        const content = await readFile(path)
        setFileContent(content)
        setSelectedPath(path)
      } finally {
        setLoadingFile(false)
      }
    },
    [readFile],
  )

  const handleSave = useCallback(
    async (content: string) => {
      if (!selectedPath) return
      await writeFile(selectedPath, content)
      setFileContent(content)
    },
    [selectedPath, writeFile],
  )

  const handleNewNote = async () => {
    const folder = prompt(
      `Save to folder (${RESEARCH_FOLDERS.join(' / ')}):`,
      'Research',
    )
    if (!folder?.trim()) return
    const name = prompt('File name (e.g. industry-analysis.md):')
    if (!name?.trim()) return
    const path = `${folder.trim()}/${name.trim().endsWith('.md') ? name.trim() : name.trim() + '.md'}`
    await writeFile(path, '')
    await refreshTree()
    await openFile(path)
  }

  // Auto-open first file when tab mounts if available
  useEffect(() => {
    if (!selectedPath && allFiles.length > 0) {
      openFile(allFiles[0].path)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree])

  return (
    <div className="h-full flex overflow-hidden">
      {/* Sidebar — file list */}
      <div className="w-44 shrink-0 border-r border-[#e0e0e0] bg-[#f4f4f4] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-2 py-2 border-b border-[#e0e0e0]">
          <span className="text-xs font-medium text-[#525252]">Notes</span>
          <div className="flex items-center gap-0.5">
            <button
              className="p-1 text-[#525252] hover:text-[#161616] hover:bg-[#e8e8e8] rounded transition-colors disabled:opacity-40"
              title={selectedPath ? 'Print current note' : 'Open a note to print'}
              onClick={handlePrintNote}
              disabled={!selectedPath}
            >
              <Printer size={13} />
            </button>
            <button
              className="p-1 text-[#525252] hover:text-[#161616] hover:bg-[#e8e8e8] rounded transition-colors"
              title="New note"
              onClick={handleNewNote}
            >
              <FilePlus size={13} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-1">
          {allFiles.length === 0 ? (
            <p className="text-xs text-[#a8a8a8] px-3 py-4 leading-relaxed">
              Add research notes here, or ask an agent to generate industry analysis
            </p>
          ) : (
            allFiles.map((file) => (
              <button
                key={file.path}
                onClick={() => openFile(file.path)}
                className={`w-full text-left px-3 py-1.5 text-xs truncate transition-colors ${
                  selectedPath === file.path
                    ? 'bg-[#0f62fe] text-white'
                    : 'text-[#525252] hover:bg-[#e8e8e8] hover:text-[#161616]'
                }`}
              >
                {file.name}
              </button>
            ))
          )}
        </div>
      </div>

      {/* Editor area */}
      <div className="flex-1 min-w-0 overflow-hidden">
        {loadingFile ? (
          <div className="flex items-center justify-center h-full">
            <span className="text-xs text-[#8d8d8d]">Loading…</span>
          </div>
        ) : selectedPath ? (
          <MarkdownEditor
            key={selectedPath}
            content={fileContent}
            filePath={selectedPath}
            onSave={handleSave}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <p className="text-xs text-[#a8a8a8] text-center px-6">
              Add research notes here, or ask an agent to generate industry analysis
            </p>
            <button
              className="flex items-center gap-1 px-3 py-1.5 text-xs text-[#0f62fe] hover:bg-[#edf4ff] rounded transition-colors"
              onClick={handleNewNote}
            >
              <FilePlus size={13} />
              New Note
            </button>
          </div>
        )}
      </div>

      {/* Hidden flat-render print portal for the current note */}
      <div
        ref={noteRef}
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: '-9999px',
          top: 0,
          width: '768px',
          background: 'white',
          padding: '48px 64px',
        }}
      >
        {selectedPath && (
          <>
            <div style={{ borderBottom: '2px solid #0f62fe', paddingBottom: '16px', marginBottom: '32px' }}>
              <p style={{ fontSize: '10px', color: '#6f6f6f', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600, marginBottom: '4px' }}>
                Research Note
              </p>
              <h1 style={{ fontSize: '20px', fontWeight: 700, color: '#161616' }}>
                {selectedPath.split('/').pop()}
              </h1>
              <p style={{ fontSize: '12px', color: '#525252', marginTop: '4px' }}>
                {selectedPath} · Printed {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
              </p>
            </div>
            <MarkdownViewer content={fileContent} />
          </>
        )}
      </div>
    </div>
  )
}
