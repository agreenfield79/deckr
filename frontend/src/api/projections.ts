/**
 * Projections API client — reads from GET /api/projections/output?deal_id=
 * Data is written by projections_service.run_projections() after the risk agent (IP3).
 */

const API_BASE = import.meta.env.VITE_API_URL ?? ''

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ProjectionRow {
  scenario: 'base' | 'upside' | 'stress'
  year: number
  revenue: number
  ebitda: number
  dscr: number | null
  funded_debt_to_ebitda: number | null
  free_cash_flow: number
}

export interface CovenantRow {
  scenario: 'base' | 'upside' | 'stress'
  year: number
  covenant_type: string
  computed_value: number | null
  threshold_value: number | null
  status: 'pass' | 'warn' | 'breach' | null
  is_breach_year: boolean
}

export interface ProjectionsOutput {
  deal_id: string
  projections: ProjectionRow[]
  covenant_compliance: CovenantRow[]
}

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

export async function getProjectionsOutput(dealId: string): Promise<ProjectionsOutput | null> {
  if (!dealId) return null
  try {
    const res = await fetch(`${API_BASE}/api/projections/output?deal_id=${encodeURIComponent(dealId)}`)
    if (!res.ok) return null
    const data = await res.json()
    if (data.status === 'error' || !data.projections) return null
    return data as ProjectionsOutput
  } catch {
    return null
  }
}
