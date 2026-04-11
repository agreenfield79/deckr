import { useState } from 'react'
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  FileText,
} from 'lucide-react'
import clsx from 'clsx'
import type { TreeNode } from '../types/workspace'

interface FileTreeNodeProps {
  node: TreeNode
  depth?: number
  activePath: string | null
  onFileClick: (path: string) => void
}

export default function FileTreeNode({
  node,
  depth = 0,
  activePath,
  onFileClick,
}: FileTreeNodeProps) {
  const [expanded, setExpanded] = useState(true)
  const indent = 8 + depth * 12

  if (node.type === 'folder') {
    return (
      <div>
        <button
          className="w-full flex items-center gap-1.5 py-1 text-xs text-[#525252] hover:text-[#161616] hover:bg-[#e8e8e8] rounded transition-colors text-left"
          style={{ paddingLeft: `${indent}px`, paddingRight: '8px' }}
          onClick={() => setExpanded(!expanded)}
        >
          <span className="shrink-0 text-[#8d8d8d]">
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
          <span className="shrink-0 text-[#8d8d8d]">
            {expanded ? <FolderOpen size={13} /> : <Folder size={13} />}
          </span>
          <span className="truncate font-medium">{node.name}</span>
        </button>
        {expanded && node.children && (
          <div>
            {node.children.map((child) => (
              <FileTreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                activePath={activePath}
                onFileClick={onFileClick}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  const isActive = node.path === activePath

  return (
    <button
      className={clsx(
        'w-full flex items-center gap-1.5 py-1 text-xs rounded transition-colors text-left',
        isActive
          ? 'bg-[#0f62fe] text-white'
          : 'text-[#525252] hover:text-[#161616] hover:bg-[#e8e8e8]',
      )}
      style={{ paddingLeft: `${indent}px`, paddingRight: '8px' }}
      onClick={() => onFileClick(node.path)}
    >
      <span className={clsx('shrink-0', isActive ? 'text-blue-200' : 'text-[#8d8d8d]')}>
        <FileText size={13} />
      </span>
      <span className="truncate">{node.name}</span>
    </button>
  )
}
