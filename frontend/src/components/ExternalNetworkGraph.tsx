/**
 * ExternalNetworkGraph — Layer 5B enrichment graph (NewsArticle, LegalEvent, Lien, etc.)
 * Collapsed by default with "Load External Network" trigger.
 */

import { useState, useCallback, useRef } from 'react'
import { Globe, RefreshCw, Loader2, Maximize2, ChevronDown, ChevronRight } from 'lucide-react'
import { getCurrentDeal } from '../api/pipelineRuns'
import { getExternalGraph } from '../api/financials'
import type { GraphResponse, GraphNode } from '../api/financials'
import GraphNodeDrawer from './GraphNodeDrawer'

const NODE_COLORS: Record<string, string> = {
  NewsArticle:     '#da1e28',
  LegalAction:     '#e8a838',
  LegalEvent:      '#e8a838',  // alias — kept for backwards compat
  Lien:            '#ff832b',
  UccFiling:       '#ff832b',
  Address:         '#6929c4',
  RegisteredAgent: '#007d79',
  Review:          '#8a3ffc',
  Company:         '#0f62fe',
}

/**
 * Resolves the authoritative graph node ID from a property dict by scanning
 * every known PK field in priority order. Identical to the helper in DealGraph.tsx.
 * Edge source/target dicts from the backend carry no label info, so label
 * dispatch is not possible — a full property scan is the only reliable approach.
 */
function getNodeIdFromProps(props: Record<string, unknown>): string | null {
  return (
    (props.entity_id       as string) ||
    (props.collateral_id   as string) ||
    (props.naics_code      as string) ||
    (props.deal_id         as string) ||
    (props.document_id     as string) ||
    (props.pipeline_run_id as string) ||
    (props.article_id      as string) ||
    (props.case_id         as string) ||
    (props.action_id       as string) ||
    (props.lien_id         as string) ||
    (props.address_id      as string) ||
    (props.agent_id        as string) ||
    (props.review_id       as string) ||
    (props.filing_id       as string) ||
    (props.node_id         as string) ||
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
    (node.title as string) ||
    (node.event_type as string) ||
    (node.name as string) ||
    (node.address_line as string) ||
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
        data: { id: `e${i}`, source: sourceId, target: targetId, label: r.type || '' },
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

export default function ExternalNetworkGraph() {
  const cyRef = useRef<cytoscape.Core | null>(null)
  const [open, setOpen] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [CytoscapeComponent, setCytoscapeComponent] = useState<React.ComponentType<any> | null>(null)

  const load = useCallback(async () => {
    if (loaded) return
    setLoading(true)
    setError(null)
    try {
      const [mod, deal] = await Promise.all([
        import('react-cytoscapejs').catch(() => null),
        getCurrentDeal(),
      ])
      if (mod) setCytoscapeComponent(() => mod.default)
      else { setError('react-cytoscapejs not installed'); return }
      if (!deal.deal_id) { setError('No deal loaded'); return }
      const g = await getExternalGraph(deal.deal_id)
      setGraph(g)
      setLoaded(true)
    } catch {
      setError('Failed to load external network')
    } finally {
      setLoading(false)
    }
  }, [loaded])

  const handleToggle = () => {
    const next = !open
    setOpen(next)
    if (next && !loaded) load()
  }

  const layout = { name: 'cose', animate: true, nodeRepulsion: 4096, idealEdgeLength: 80 }
  const stylesheet = [
    { selector: 'node', style: { 'background-color': 'data(color)', label: 'data(label)', color: '#fff', 'font-size': 9, width: 34, height: 34, 'text-valign': 'center', 'text-halign': 'center', 'text-wrap': 'wrap', 'text-max-width': 60 } as Record<string, unknown> },
    { selector: 'edge', style: { width: 1.5, 'line-color': '#c6c6c6', 'target-arrow-color': '#c6c6c6', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: '#8d8d8d' } as Record<string, unknown> },
  ]

  const nodeCount = graph?.nodes.length ?? 0

  return (
    <div className="border border-[#e0e0e0] rounded bg-white overflow-hidden mt-3">
      <button
        className="w-full flex items-center justify-between px-3 py-2.5 bg-[#f4f4f4] hover:bg-[#e8e8e8] transition-colors"
        onClick={handleToggle}
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown size={12} className="text-[#525252]" /> : <ChevronRight size={12} className="text-[#525252]" />}
          <Globe size={13} className="text-[#da1e28]" />
          <span className="text-xs font-semibold text-[#161616]">External Network Graph</span>
          <span className="text-[10px] text-[#8d8d8d]">Layer 5B — enrichment data</span>
        </div>
        {loaded && nodeCount > 0 && (
          <span className="text-[10px] text-[#8d8d8d]">{nodeCount} nodes</span>
        )}
      </button>

      {open && (
        <div className="relative border-t border-[#e0e0e0]" style={{ height: 320 }}>
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
              <Loader2 size={20} className="animate-spin text-[#da1e28]" />
            </div>
          )}
          {error && (
            <div className="flex items-center justify-center h-full">
              <p className="text-xs text-[#a8a8a8] italic text-center px-6">{error}</p>
            </div>
          )}
          {!error && !loading && graph && CytoscapeComponent && graph.nodes.length > 0 && (
            <>
              <div className="flex items-center justify-end px-2 py-1 border-b border-[#f4f4f4]">
                <button onClick={() => cyRef.current?.fit()} title="Fit" className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded">
                  <Maximize2 size={11} />
                </button>
                <button onClick={load} disabled={loading} className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded ml-1">
                  <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
                </button>
              </div>
              <CytoscapeComponent
                elements={buildElements(graph)}
                layout={layout}
                stylesheet={stylesheet}
                style={{ width: '100%', height: 'calc(100% - 28px)' }}
                cy={(cy: cytoscape.Core) => {
                  cyRef.current = cy
                  cy.on('tap', 'node', (evt) => setSelectedNode(evt.target.data() as GraphNode))
                  cy.on('tap', (evt) => { if (evt.target === cy) setSelectedNode(null) })
                }}
              />
            </>
          )}
          {!error && !loading && loaded && graph?.nodes.length === 0 && (
            <div className="flex items-center justify-center h-full">
              <p className="text-xs text-[#a8a8a8] italic">
                No external enrichment nodes found for this deal.
              </p>
            </div>
          )}
          {selectedNode && <GraphNodeDrawer node={selectedNode} onClose={() => setSelectedNode(null)} />}
        </div>
      )}
    </div>
  )
}
