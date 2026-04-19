/**
 * DealGraph — Layer 5A deal structure graph using Cytoscape.js.
 * Node types: Company (IBM Blue), Individual (Orange), Loan (Green),
 *             Collateral (Purple), Industry (Teal)
 * Requires: react-cytoscapejs, cytoscape, cytoscape-cose-bilkent
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { Network, RefreshCw, Loader2, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react'
import { getCurrentDeal } from '../api/pipelineRuns'
import { getDealGraph } from '../api/financials'
import type { GraphResponse, GraphNode } from '../api/financials'
import GraphNodeDrawer from './GraphNodeDrawer'

const NODE_COLORS: Record<string, string> = {
  Company:    '#0f62fe',
  Individual: '#ff832b',
  Loan:       '#24a148',
  Collateral: '#8a3ffc',
  Industry:   '#007d79',
  Deal:       '#0f62fe',
}

/**
 * Resolves the authoritative graph node ID from a properties dict by scanning
 * every known PK field in priority order. Used for both node element building
 * and edge source/target resolution — edge objects from /api/graph/deal carry
 * only raw property dicts with no label info, so label dispatch is not possible.
 * DD-authoritative PK mapping:
 *   Company/Individual → entity_id | Loan → deal_id | Collateral → collateral_id
 *   Industry → naics_code | Document → document_id | PipelineRun → pipeline_run_id
 *   5B types → article_id / case_id / action_id / lien_id / address_id / agent_id /
 *              review_id / filing_id | generic fallback → node_id
 */
function getNodeIdFromProps(props: Record<string, unknown>): string | null {
  return (
    (props.entity_id      as string) ||
    (props.collateral_id  as string) ||
    (props.naics_code     as string) ||
    (props.deal_id        as string) ||
    (props.document_id    as string) ||
    (props.pipeline_run_id as string) ||
    (props.article_id     as string) ||
    (props.case_id        as string) ||
    (props.action_id      as string) ||
    (props.lien_id        as string) ||
    (props.address_id     as string) ||
    (props.agent_id       as string) ||
    (props.review_id      as string) ||
    (props.filing_id      as string) ||
    (props.node_id        as string) ||
    null
  )
}

function nodeColor(labels: string[]): string {
  for (const l of labels) {
    if (NODE_COLORS[l]) return NODE_COLORS[l]
  }
  return '#525252'
}

function nodeLabel(node: GraphNode): string {
  return (
    (node.legal_name as string) ||
    (node.company_name as string) ||
    (node.name as string) ||
    (node.loan_purpose as string) ||
    (node.labels as string[])?.[0] ||
    'Node'
  )
}

function buildElements(graph: GraphResponse) {
  const nodes = graph.nodes.map((n, i) => ({
    data: {
      id: getNodeIdFromProps(n as Record<string, unknown>) ?? String(i),
      label: nodeLabel(n),
      color: nodeColor(n.labels),
      ...n,
    },
  }))

  const nodeIdSet = new Set(nodes.map((n) => n.data.id))

  const edges = graph.relationships
    .map((r, i) => {
      const sourceId = getNodeIdFromProps(r.source as Record<string, unknown>)
      const targetId = getNodeIdFromProps(r.target as Record<string, unknown>)
      if (!sourceId || !targetId) return null
      return {
        data: {
          id: `e${i}`,
          source: sourceId,
          target: targetId,
          label: r.type || '',
        },
      }
    })
    .filter(
      (e): e is NonNullable<typeof e> =>
        e !== null &&
        nodeIdSet.has(e.data.source) &&
        nodeIdSet.has(e.data.target),
    )

  return [...nodes, ...edges]
}

export default function DealGraph() {
  const cyRef = useRef<cytoscape.Core | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [CytoscapeComponent, setCytoscapeComponent] = useState<React.ComponentType<any> | null>(null)

  // Lazy-load react-cytoscapejs to avoid import errors if not yet installed
  useEffect(() => {
    import('react-cytoscapejs').then((mod) => {
      setCytoscapeComponent(() => mod.default)
    }).catch(() => setError('react-cytoscapejs not installed — run: npm install react-cytoscapejs cytoscape'))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const deal = await getCurrentDeal()
      if (!deal.deal_id) { setError('No deal loaded'); return }
      const g = await getDealGraph(deal.deal_id)
      if (!g) { setError('No graph data — run pipeline first'); return }
      setGraph(g)
    } catch {
      setError('Failed to load deal graph')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const layout = {
    name: 'cose',
    animate: true,
    randomize: false,
    nodeRepulsion: 4096,
    idealEdgeLength: 80,
  }

  const stylesheet = [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        label: 'data(label)',
        color: '#ffffff',
        'font-size': 10,
        'text-wrap': 'wrap',
        'text-max-width': 80,
        width: 40,
        height: 40,
        'text-valign': 'center',
        'text-halign': 'center',
        'font-weight': 600,
      } as Record<string, unknown>,
    },
    {
      selector: 'edge',
      style: {
        width: 1.5,
        'line-color': '#c6c6c6',
        'target-arrow-color': '#c6c6c6',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        label: 'data(label)',
        'font-size': 8,
        color: '#8d8d8d',
        'text-background-color': '#ffffff',
        'text-background-opacity': 0.9,
        'text-background-padding': '2px',
      } as Record<string, unknown>,
    },
  ]

  const nodeCount = graph?.nodes.length ?? 0
  const edgeCount = graph?.relationships.length ?? 0

  return (
    <div className="relative border border-[#e0e0e0] rounded bg-white overflow-hidden" style={{ height: 360 }}>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-[#f4f4f4] border-b border-[#e0e0e0]">
        <div className="flex items-center gap-2">
          <Network size={13} className="text-[#0f62fe]" />
          <span className="text-xs font-semibold text-[#161616]">Deal Structure Graph</span>
          {graph && (
            <span className="text-[10px] text-[#8d8d8d]">
              {nodeCount} nodes · {edgeCount} edges
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => cyRef.current?.fit()}
            title="Fit to screen"
            className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded transition-colors"
          >
            <Maximize2 size={12} />
          </button>
          <button
            onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.2)}
            title="Zoom in"
            className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded transition-colors"
          >
            <ZoomIn size={12} />
          </button>
          <button
            onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 0.8)}
            title="Zoom out"
            className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded transition-colors"
          >
            <ZoomOut size={12} />
          </button>
          <button
            onClick={load}
            disabled={loading}
            title="Reload graph"
            className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 px-3 py-1 border-b border-[#e0e0e0] bg-white">
        {Object.entries(NODE_COLORS).slice(0, 5).map(([label, color]) => (
          <span key={label} className="flex items-center gap-1 text-[9px] text-[#525252]">
            <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: color }} />
            {label}
          </span>
        ))}
      </div>

      {/* Graph area */}
      <div className="relative" style={{ height: 'calc(100% - 62px)' }}>
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
            <Loader2 size={20} className="animate-spin text-[#0f62fe]" />
          </div>
        )}
        {error && !loading && (
          <div className="flex items-center justify-center h-full">
            <p className="text-xs text-[#a8a8a8] italic text-center px-6">{error}</p>
          </div>
        )}
        {!error && !loading && graph && CytoscapeComponent && (
          <CytoscapeComponent
            elements={buildElements(graph)}
            layout={layout}
            stylesheet={stylesheet}
            style={{ width: '100%', height: '100%' }}
            cy={(cy: cytoscape.Core) => {
              cyRef.current = cy
              cy.on('tap', 'node', (evt) => {
                const nodeData = evt.target.data() as GraphNode
                setSelectedNode(nodeData)
              })
              cy.on('tap', (evt) => {
                if (evt.target === cy) setSelectedNode(null)
              })
            }}
          />
        )}
        {!error && !loading && (!graph || graph.nodes.length === 0) && (
          <div className="flex items-center justify-center h-full">
            <p className="text-xs text-[#a8a8a8] italic">
              No graph nodes yet — run the pipeline to populate Neo4j.
            </p>
          </div>
        )}

        {/* Node drawer */}
        {selectedNode && (
          <GraphNodeDrawer node={selectedNode} onClose={() => setSelectedNode(null)} />
        )}
      </div>
    </div>
  )
}
