import { useState, useEffect, useCallback } from 'react'
import { FilePlus } from 'lucide-react'
import { useProject } from '../context/ProjectContext'
import MarkdownEditor from '../editor/MarkdownEditor'
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
          <button
            className="p-1 text-[#525252] hover:text-[#161616] hover:bg-[#e8e8e8] rounded transition-colors"
            title="New note"
            onClick={handleNewNote}
          >
            <FilePlus size={13} />
          </button>
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
    </div>
  )
}
