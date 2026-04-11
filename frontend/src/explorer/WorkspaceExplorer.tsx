import { useState, useRef, useCallback, useEffect } from 'react'
import { FilePlus, FolderPlus, RefreshCw, Search } from 'lucide-react'
import FileTreeNode from './FileTreeNode'
import ContextMenu, { type ContextMenuState } from './ContextMenu'
import { useProject } from '../context/ProjectContext'
import * as workspaceApi from '../api/workspace'
import type { TreeNode } from '../types/workspace'

function filterTree(nodes: TreeNode[], query: string): TreeNode[] {
  if (!query) return nodes
  const q = query.toLowerCase()
  const results: TreeNode[] = []
  for (const node of nodes) {
    if (node.type === 'file') {
      if (node.name.toLowerCase().includes(q)) results.push(node)
    } else {
      const filtered = filterTree(node.children ?? [], q)
      if (filtered.length > 0) {
        results.push({ ...node, children: filtered })
      } else if (node.name.toLowerCase().includes(q)) {
        results.push(node)
      }
    }
  }
  return results
}

// Skeleton placeholder rows shown while the tree loads
function TreeSkeleton() {
  const widths = [72, 56, 88, 48, 64, 40]
  return (
    <div className="py-2 px-1.5 space-y-0.5">
      {widths.map((w, i) => (
        <div key={i} className="flex items-center gap-1.5 py-1 px-2">
          <div className="w-3 h-3 bg-[#e0e0e0] rounded animate-pulse shrink-0" />
          <div
            className="h-2.5 bg-[#e0e0e0] rounded animate-pulse"
            style={{ width: `${w}px` }}
          />
        </div>
      ))}
    </div>
  )
}

export default function WorkspaceExplorer() {
  const {
    tree,
    treeLoading,
    openFile,
    activeFile,
    refreshTree,
    writeFile,
    createFolder,
    deleteFile,
  } = useProject()

  const [search, setSearch] = useState('')
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const savedScrollRef = useRef(0)

  // Preserve scroll position across tree refreshes
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    savedScrollRef.current = e.currentTarget.scrollTop
  }, [])

  useEffect(() => {
    if (!treeLoading && scrollRef.current) {
      scrollRef.current.scrollTop = savedScrollRef.current
    }
  }, [tree, treeLoading])

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

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, node: TreeNode) => {
      e.preventDefault()
      setContextMenu({ node, x: e.clientX, y: e.clientY })
    },
    [],
  )

  const handleRename = async (node: TreeNode) => {
    const newName = prompt(`Rename "${node.name}" to:`, node.name)
    if (!newName?.trim() || newName.trim() === node.name) return
    const parent = node.path.includes('/')
      ? node.path.substring(0, node.path.lastIndexOf('/'))
      : ''
    const newPath = parent ? `${parent}/${newName.trim()}` : newName.trim()
    try {
      await workspaceApi.renameFile(node.path, newPath)
      await refreshTree()
    } catch {
      alert('Rename failed. Check that the backend is running.')
    }
  }

  const handleDelete = async (node: TreeNode) => {
    if (!confirm(`Delete "${node.name}"? This cannot be undone.`)) return
    try {
      await deleteFile(node.path)
    } catch {
      alert('Delete failed. Check that the backend is running.')
    }
  }

  const displayTree = filterTree(tree, search)

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

      {/* Search */}
      <div className="px-2 py-1.5 border-b border-[#e0e0e0] shrink-0">
        <div className="flex items-center gap-1.5 bg-white border border-[#e0e0e0] rounded px-2 py-1 focus-within:border-[#0f62fe] transition-colors">
          <Search size={11} className="text-[#a8a8a8] shrink-0" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search files…"
            className="flex-1 text-xs text-[#161616] bg-transparent outline-none placeholder:text-[#a8a8a8]"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="text-[#a8a8a8] hover:text-[#525252] text-xs leading-none"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Tree */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto py-1 px-1"
        onScroll={handleScroll}
      >
        {treeLoading && tree.length === 0 ? (
          <TreeSkeleton />
        ) : displayTree.length === 0 ? (
          <p className="text-xs text-[#a8a8a8] text-center px-3 py-6 leading-relaxed">
            {search
              ? `No files match "${search}"`
              : 'No files yet — complete the onboarding form to get started'}
          </p>
        ) : (
          displayTree.map((node) => (
            <FileTreeNode
              key={node.path}
              node={node}
              activePath={activeFile?.path ?? null}
              onFileClick={openFile}
              onContextMenu={handleContextMenu}
            />
          ))
        )}
      </div>

      {/* Context menu portal */}
      {contextMenu && (
        <ContextMenu
          menu={contextMenu}
          onOpen={(node) => openFile(node.path)}
          onRename={handleRename}
          onDelete={handleDelete}
          onClose={() => setContextMenu(null)}
        />
      )}
    </div>
  )
}
