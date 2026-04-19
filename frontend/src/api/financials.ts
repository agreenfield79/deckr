import { getFile } from './workspace'
import { get } from './client'

export interface FiscalYearValues {
  [year: string]: number | null
}

export interface ExtractedFinancials {
  company: string
  document_type: string
  fiscal_years: string[]
  income_statement: {
    revenue: FiscalYearValues
    gross_profit: FiscalYearValues
    ebitda: FiscalYearValues
    operating_income: FiscalYearValues
    net_income: FiscalYearValues
    interest_expense: FiscalYearValues
    depreciation_amortization: FiscalYearValues
  }
  balance_sheet: {
    total_assets: FiscalYearValues
    total_liabilities: FiscalYearValues
    total_equity: FiscalYearValues
    cash: FiscalYearValues
    current_assets: FiscalYearValues
    current_liabilities: FiscalYearValues
    total_debt: FiscalYearValues
    long_term_debt: FiscalYearValues
  }
  cash_flow_statement: {
    operating_cash_flow: FiscalYearValues
    capex: FiscalYearValues
    free_cash_flow: FiscalYearValues
  }
  metadata: {
    source_files: string[]
    missing_fields: string[]
    extracted_at: string
  }
}

export async function getExtractedFinancials(): Promise<ExtractedFinancials | null> {
  try {
    const res = await getFile('Financials/extracted_data.json')
    if (!res.content) return null
    return JSON.parse(res.content) as ExtractedFinancials
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// SQL-backed ratio and covenant types
// ---------------------------------------------------------------------------

export interface RatioRow {
  fiscal_year: number
  historical_dscr: number | null
  fixed_charge_coverage: number | null
  leverage_ratio: number | null
  funded_debt_to_ebitda: number | null
  current_ratio: number | null
  ebitda_margin: number | null
}

export interface CovenantRow {
  metric: string
  description: string | null
  threshold_value: number | null
  actual_value: number | null
  pass_fail: boolean | null
  source_agent: string | null
}

export interface FinancialSummaryRow {
  fiscal_year: number
  revenue: number | null
  gross_profit: number | null
  ebitda: number | null
  ebit: number | null
  net_income: number | null
  interest_expense: number | null
  depreciation_amortization: number | null
  operating_expenses: number | null
}

export interface BalanceSummaryRow {
  total_assets: number | null
  total_liabilities: number | null
  total_equity: number | null
  current_assets: number | null
  current_liabilities: number | null
  cash: number | null
  long_term_debt: number | null
  short_term_debt: number | null
}

export interface CashFlowSummaryRow {
  fiscal_year: number
  operating_cash_flow: number | null
  capex: number | null
  free_cash_flow: number | null
}

export interface FinancialSummaryResponse {
  deal_id: string
  income_statement: FinancialSummaryRow[]
  balance_sheet: BalanceSummaryRow[]
  cash_flow: CashFlowSummaryRow[]
}

export async function getRatios(dealId: string): Promise<RatioRow[]> {
  try {
    const res = await get<{ ratios: RatioRow[] }>(`/financials/ratios/${dealId}`)
    return res.ratios ?? []
  } catch {
    return []
  }
}

export async function getCovenants(dealId: string): Promise<CovenantRow[]> {
  try {
    const res = await get<{ covenants: CovenantRow[] }>(`/financials/covenants/${dealId}`)
    return res.covenants ?? []
  } catch {
    return []
  }
}

export async function getFinancialSummary(dealId: string): Promise<FinancialSummaryResponse | null> {
  try {
    const res = await get<FinancialSummaryResponse & { status?: string }>(
      `/financials/summary?deal_id=${encodeURIComponent(dealId)}`
    )
    if (res.status === 'error') return null
    return res
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// SLACR components
// ---------------------------------------------------------------------------

export interface SlacrComponents {
  sponsor_score: number | null
  leverage_score: number | null
  asset_quality_score: number | null
  cash_flow_score: number | null
  risk_score: number | null
  composite_score: number | null
  internal_rating: string
  occ_classification: string
  model_version: string | null
  computed_at: string | null
}

export async function getSlacrComponents(dealId: string): Promise<SlacrComponents | null> {
  try {
    const res = await get<{ components: SlacrComponents | null }>(`/slacr/components?deal_id=${encodeURIComponent(dealId)}`)
    return res.components ?? null
  } catch {
    return null
  }
}

export interface ShapLimeResponse {
  shap_values: Record<string, number> | null
  lime_values: Record<string, number> | null
  composite_score: number | null
  internal_rating: string | null
}

export async function getShapLime(dealId: string): Promise<ShapLimeResponse | null> {
  try {
    const res = await get<ShapLimeResponse & { status?: string }>(`/slacr/shap-lime?deal_id=${encodeURIComponent(dealId)}`)
    if (res.status === 'error') return null
    return res
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Graph endpoints
// ---------------------------------------------------------------------------

export interface GraphNode {
  labels: string[]
  [key: string]: unknown
}

export interface GraphEdge {
  source: Record<string, unknown>
  type: string
  target: Record<string, unknown>
}

export interface GraphResponse {
  nodes: GraphNode[]
  relationships: GraphEdge[]
}

export async function getDealGraph(dealId: string): Promise<GraphResponse | null> {
  try {
    const res = await get<{ graph: GraphResponse }>(`/graph/deal?deal_id=${encodeURIComponent(dealId)}`)
    return res.graph ?? null
  } catch {
    return null
  }
}

export async function getExternalGraph(dealId: string): Promise<GraphResponse | null> {
  try {
    const res = await get<{ graph: GraphResponse }>(`/graph/external?deal_id=${encodeURIComponent(dealId)}`)
    return res.graph ?? null
  } catch {
    return null
  }
}

export async function getGraphNode(nodeId: string): Promise<GraphNode | null> {
  try {
    const res = await get<{ node: GraphNode | null }>(`/graph/node/${encodeURIComponent(nodeId)}`)
    return res.node ?? null
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// MongoDB endpoints
// ---------------------------------------------------------------------------

export interface WordCloudTerm {
  text: string
  value: number
  weight: number
}

export async function getWordCloud(dealId: string): Promise<WordCloudTerm[]> {
  try {
    const res = await get<{ terms: WordCloudTerm[] }>(`/mongo/word-cloud?deal_id=${encodeURIComponent(dealId)}`)
    return res.terms ?? []
  } catch {
    return []
  }
}

export interface DocumentCoverageResponse {
  agents: string[]
  documents: Array<{
    document: string
    document_type: string
    coverage: Record<string, boolean>
  }>
}

export async function getDocumentCoverage(dealId: string): Promise<DocumentCoverageResponse | null> {
  try {
    const res = await get<DocumentCoverageResponse & { status?: string }>(
      `/mongo/document-coverage?deal_id=${encodeURIComponent(dealId)}`
    )
    if (res.status === 'error') return null
    return res
  } catch {
    return null
  }
}

export interface PipelineTimelineRun {
  pipeline_run_id: string
  deal_id: string
  status: string
  started_at: string
  completed_at?: string
  total_elapsed_ms?: number
  stages: Array<{
    agent_name: string
    stage_order: number
    status: string
    elapsed_ms: number
    started_at?: string
    completed_at?: string
  }>
}

export async function getPipelineTimeline(dealId?: string, limit = 5): Promise<PipelineTimelineRun[]> {
  try {
    const params = new URLSearchParams({ limit: String(limit) })
    if (dealId) params.set('deal_id', dealId)
    const res = await get<{ runs: PipelineTimelineRun[] }>(`/mongo/pipeline-timeline?${params}`)
    return res.runs ?? []
  } catch {
    return []
  }
}
