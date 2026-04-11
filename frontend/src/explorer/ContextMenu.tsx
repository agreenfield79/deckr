import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { FolderOpen, PencilLine, Trash2 } from 'lucide-react'
import type { TreeNode } from '../types/workspace'

export interface ContextMenuState {
  node: TreeNode
  x: number
  y: number
}

interface ContextMenuProps {
  menu: ContextMenuState
  onOpen: (node: TreeNode) => void
  onRename: (node: TreeNode) => void
  onDelete: (node: TreeNode) => void
  onClose: () => void
}

export default function ContextMenu({
  menu,
  onOpen,
  onRename,
  onDelete,
  onClose,
}: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)

  // Close on outside click or Escape
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [onClose])

  // Keep menu on screen
  const style: React.CSSProperties = {
    position: 'fixed',
    top: Math.min(menu.y, window.innerHeight - 120),
    left: Math.min(menu.x, window.innerWidth - 160),
    zIndex: 9999,
  }

  return createPortal(
    <div
      ref={menuRef}
      style={style}
      className="w-40 bg-white border border-[#c6c6c6] rounded shadow-lg py-1 text-xs"
      onContextMenu={(e) => e.preventDefault()}
    >
      {menu.node.type === 'file' && (
        <MenuItem
          icon={<FolderOpen size={13} />}
          label="Open"
          onClick={() => { onOpen(menu.node); onClose() }}
        />
      )}
      <MenuItem
        icon={<PencilLine size={13} />}
        label="Rename"
        onClick={() => { onRename(menu.node); onClose() }}
      />
      <div className="my-1 border-t border-[#e0e0e0]" />
      <MenuItem
        icon={<Trash2 size={13} />}
        label="Delete"
        danger
        onClick={() => { onDelete(menu.node); onClose() }}
      />
    </div>,
    document.body,
  )
}

function MenuItem({
  icon,
  label,
  danger = false,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  danger?: boolean
  onClick: () => void
}) {
  return (
    <button
      className={`w-full flex items-center gap-2 px-3 py-1.5 text-left transition-colors ${
        danger
          ? 'text-[#da1e28] hover:bg-[#fff1f1]'
          : 'text-[#161616] hover:bg-[#e8e8e8]'
      }`}
      onClick={onClick}
    >
      <span className={danger ? 'text-[#da1e28]' : 'text-[#525252]'}>{icon}</span>
      {label}
    </button>
  )
}
