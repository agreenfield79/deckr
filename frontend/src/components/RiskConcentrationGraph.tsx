/**
 * RiskConcentrationGraph — Cytoscape subgraph of Guarantors + Loan + Collateral.
 * Shows GUARANTEES edges weighted by coverage ratio.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { ShieldCheck, RefreshCw, Loader2, Maximize2 } from 'lucide-react'
import { getCurrentDeal } from '../api/pipelineRuns'
import { getDealGraph } from '../api/financials'
import type { GraphResponse, GraphNode } from '../api/financials'
import GraphNodeDrawer from './GraphNodeDrawer'

const RISK_COLORS: Record<string, string> = {
  Individual: '#ff832b',
  Company:    '#ff832b',
  Loan:       '#24a148',
  Collateral: '#8a3ffc',
}

/**
 * Resolves the authoritative graph node ID from a property dict by scanning
 * every known PK field in priority order. Identical to the helper in DealGraph.tsx.
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

function buildRiskElements(graph: GraphResponse) {
  const riskLabels = new Set(['Individual', 'Loan', 'Collateral', 'Company'])
  const riskNodes = graph.nodes.filter((n) =>
    n.labels.some((l) => riskLabels.has(l))
  )

  const riskIds = new Set(
    riskNodes.map((n) => getNodeIdFromProps(n as Record<string, unknown>)).filter(Boolean) as string[]
  )

  const riskEdges = graph.relationships.filter((r) => {
    const srcId = getNodeIdFromProps(r.source as Record<string, unknown>)
    const tgtId = getNodeIdFromProps(r.target as Record<string, unknown>)
    return srcId !== null && tgtId !== null && riskIds.has(srcId) && riskIds.has(tgtId)
  })

  const nodes = riskNodes.map((n, i) => {
    const color = n.labels.reduce<string>((c, l) => RISK_COLORS[l] ?? c, '#525252')
    const id = getNodeIdFromProps(n as Record<string, unknown>) ?? String(i)
    return {
      data: {
        id,
        label: (n.legal_name as string) || (n.name as string) || n.labels[0],
        color,
        ...n,
      },
    }
  })

  const nodeIdSet = new Set(nodes.map((n) => n.data.id))

  const edges = riskEdges
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

export default function RiskConcentrationGraph() {
  const cyRef = useRef<cytoscape.Core | null>(null)
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [CytoscapeComponent, setCytoscapeComponent] = useState<React.ComponentType<any> | null>(null)

  const load = useCallback(async () => {
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
      const g = await getDealGraph(deal.deal_id)
      setGraph(g)
    } catch {
      setError('Failed to load risk graph')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const elements = graph ? buildRiskElements(graph) : []
  const layout = { name: 'cose', animate: true, nodeRepulsion: 6000, idealEdgeLength: 120 }
  const stylesheet = [
    { selector: 'node', style: { 'background-color': 'data(color)', label: 'data(label)', color: '#fff', 'font-size': 10, width: 44, height: 44, 'text-valign': 'center', 'text-halign': 'center', 'text-wrap': 'wrap', 'text-max-width': 70, 'font-weight': 600 } as Record<string, unknown> },
    { selector: 'edge', style: { width: 2, 'line-color': '#c6c6c6', 'target-arrow-color': '#c6c6c6', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: '#8d8d8d' } as Record<string, unknown> },
  ]

  return (
    <div className="relative border border-[#e0e0e0] rounded bg-white overflow-hidden mt-3" style={{ height: 300 }}>
      <div className="flex items-center justify-between px-3 py-2 bg-[#f4f4f4] border-b border-[#e0e0e0]">
        <div className="flex items-center gap-2">
          <ShieldCheck size={13} className="text-[#8a3ffc]" />
          <span className="text-xs font-semibold text-[#161616]">Risk Concentration Graph</span>
          <span className="text-[10px] text-[#8d8d8d]">Guarantors · Loan · Collateral</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => cyRef.current?.fit()} title="Fit" className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded"><Maximize2 size={12} /></button>
          <button onClick={load} disabled={loading} className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded disabled:opacity-50"><RefreshCw size={12} className={loading ? 'animate-spin' : ''} /></button>
        </div>
      </div>

      <div className="relative" style={{ height: 'calc(100% - 40px)' }}>
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
            <Loader2 size={18} className="animate-spin text-[#8a3ffc]" />
          </div>
        )}
        {error && <div className="flex items-center justify-center h-full"><p className="text-xs text-[#a8a8a8] italic text-center px-6">{error}</p></div>}
        {!error && !loading && graph && CytoscapeComponent && elements.length > 0 && (
          <CytoscapeComponent
            elements={elements}
            layout={layout}
            stylesheet={stylesheet}
            style={{ width: '100%', height: '100%' }}
            cy={(cy: cytoscape.Core) => {
              cyRef.current = cy
              cy.on('tap', 'node', (evt) => setSelectedNode(evt.target.data() as GraphNode))
              cy.on('tap', (evt) => { if (evt.target === cy) setSelectedNode(null) })
            }}
          />
        )}
        {!error && !loading && elements.length === 0 && !loading && (
          <div className="flex items-center justify-center h-full">
            <p className="text-xs text-[#a8a8a8] italic">No guarantor/collateral nodes found.</p>
          </div>
        )}
        {selectedNode && <GraphNodeDrawer node={selectedNode} onClose={() => setSelectedNode(null)} />}
      </div>
    </div>
  )
}
