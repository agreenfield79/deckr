import { FilePlus, FolderPlus, RefreshCw } from 'lucide-react'
import FileTreeNode from './FileTreeNode'
import { useProject } from '../context/ProjectContext'

export default function WorkspaceExplorer() {
  const {
    tree,
    treeLoading,
    openFile,
    activeFile,
    refreshTree,
    writeFile,
    createFolder,
  } = useProject()

  const handleNewFile = async () => {
    const name = prompt('New file name (e.g. Research/note.md):')
    if (!name?.trim()) return
    await writeFile(name.trim(), '')
    await refreshTree()
    await openFile(name.trim())
  }

  const handleNewFolder = async () => {
    const name = prompt('New folder name:')
    if (!name?.trim()) return
    await createFolder(name.trim())
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-0.5 px-1.5 py-1.5 border-b border-[#e0e0e0] shrink-0">
        <button
          className="p-1.5 text-[#525252] hover:text-[#161616] hover:bg-[#e8e8e8] rounded transition-colors"
          title="New file"
          onClick={handleNewFile}
        >
          <FilePlus size={14} />
        </button>
        <button
          className="p-1.5 text-[#525252] hover:text-[#161616] hover:bg-[#e8e8e8] rounded transition-colors"
          title="New folder"
          onClick={handleNewFolder}
        >
          <FolderPlus size={14} />
        </button>
        <button
          className="p-1.5 text-[#525252] hover:text-[#161616] hover:bg-[#e8e8e8] rounded transition-colors ml-auto"
          title="Refresh"
          onClick={refreshTree}
        >
          <RefreshCw size={13} className={treeLoading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto py-1 px-1">
        {treeLoading && tree.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <span className="text-xs text-[#a8a8a8]">Loading…</span>
          </div>
        ) : tree.length === 0 ? (
          <p className="text-xs text-[#a8a8a8] text-center px-3 py-6 leading-relaxed">
            No files yet — complete the onboarding form to get started
          </p>
        ) : (
          tree.map((node) => (
            <FileTreeNode
              key={node.path}
              node={node}
              activePath={activeFile?.path ?? null}
              onFileClick={openFile}
            />
          ))
        )}
      </div>
    </div>
  )
}
