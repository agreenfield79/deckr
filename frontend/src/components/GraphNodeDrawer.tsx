/**
 * GraphNodeDrawer — right-side slide-out panel showing clicked node's properties.
 * Used by DealGraph, ExternalNetworkGraph, RiskConcentrationGraph.
 */

import { X } from 'lucide-react'
import type { GraphNode } from '../api/financials'

interface Props {
  node: GraphNode | null
  onClose: () => void
}

function formatValue(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export default function GraphNodeDrawer({ node, onClose }: Props) {
  if (!node) return null

  const labels = node.labels ?? []
  const props = Object.entries(node).filter(([k]) => k !== 'labels')

  return (
    <div
      className="absolute right-0 top-0 h-full w-64 bg-white border-l border-[#e0e0e0] shadow-lg z-10 flex flex-col overflow-hidden"
      style={{ maxWidth: '100%' }}
    >
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-[#e0e0e0] bg-[#f4f4f4]">
        <div>
          {labels.map((l) => (
            <span
              key={l}
              className="text-[10px] font-semibold px-1.5 py-0.5 rounded mr-1"
              style={{ backgroundColor: '#edf4ff', color: '#0043ce' }}
            >
              {l}
            </span>
          ))}
        </div>
        <button
          onClick={onClose}
          className="p-1 text-[#525252] hover:text-[#161616] hover:bg-[#e0e0e0] rounded transition-colors"
        >
          <X size={13} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
        {props.map(([key, val]) => (
          <div key={key} className="py-1 border-b border-[#f4f4f4] last:border-0">
            <p className="text-[9px] font-semibold text-[#8d8d8d] uppercase tracking-wider">{key}</p>
            <p className="text-[11px] text-[#161616] break-words">{formatValue(val)}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
