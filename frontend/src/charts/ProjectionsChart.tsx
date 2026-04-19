import { GroupedBarChart, LineChart } from '@carbon/charts-react'
import { ScaleTypes } from '@carbon/charts'
import type { ProjectionsOutput } from '../api/projections'

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const EMPTY_MSG = (msg: string) => (
  <p className="text-xs text-[#6f6f6f] italic py-3">{msg}</p>
)

function scaledLabel(value: number | null): string {
  if (value === null) return ''
  const abs = Math.abs(value)
  if (abs >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(0)}K`
  return `$${value.toFixed(0)}`
}

interface Props {
  data: ProjectionsOutput | null
  compact?: boolean  // true = ~80px height, used in DeckrPoster banner
}

// ---------------------------------------------------------------------------
// DSCR Projection Chart — Line chart (base/upside/stress) + 1.25x threshold
// ---------------------------------------------------------------------------

export function DscrProjectionChart({ data, compact = false }: Props) {
  if (!data || data.projections.length === 0) {
    return EMPTY_MSG('Projections not yet run — complete the pipeline to generate.')
  }

  const THRESHOLD = 1.25
  const years = [...new Set(data.projections.map((r) => r.year))].sort((a, b) => a - b)

  const chartData: { group: string; key: string; value: number }[] = []

  for (const year of years) {
    const key = `Y${year}`
    const byScenario = (sc: string) =>
      data.projections.find((r) => r.scenario === sc && r.year === year)?.dscr ?? null

    const base   = byScenario('base')
    const upside = byScenario('upside')
    const stress = byScenario('stress')

    if (base   != null) chartData.push({ group: 'Base DSCR',   key, value: base })
    if (upside != null) chartData.push({ group: 'Upside DSCR', key, value: upside })
    if (stress != null) chartData.push({ group: 'Stress DSCR', key, value: stress })
    chartData.push({ group: '1.25x Min', key, value: THRESHOLD })
  }

  if (chartData.length === 0) return EMPTY_MSG('DSCR data not available in projections.')

  const height = compact ? '90px' : '280px'

  const options = {
    title: compact ? '' : 'DSCR Projection — 3 Scenarios',
    axes: {
      left: {
        mapsTo: 'value',
        title: compact ? '' : 'DSCR (x)',
        ticks: { formatter: (v: number | Date) => `${(v as number).toFixed(2)}x` },
      },
      bottom: {
        mapsTo: 'key',
        scaleType: ScaleTypes.LABELS,
        title: compact ? '' : 'Projection Year',
      },
    },
    color: {
      scale: {
        'Base DSCR':   '#0f62fe',
        'Upside DSCR': '#198038',
        'Stress DSCR': '#da1e28',
        '1.25x Min':   '#f1c21b',
      },
    },
    curve: 'curveMonotoneX',
    height,
    toolbar: { enabled: false },
    legend: { enabled: !compact },
  }

  return (
    <div className={`border border-[#e0e0e0] rounded overflow-hidden ${compact ? '' : 'mt-3'}`}>
      {!compact && (
        <div className="px-3 pt-2 pb-1 bg-[#f4f4f4] border-b border-[#e0e0e0]">
          <p className="text-[10px] text-[#6f6f6f]">
            Blue = Base · Green = Upside · Red = Stress · Yellow dashed = 1.25x covenant minimum
          </p>
        </div>
      )}
      <LineChart data={chartData} options={options} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Leverage Projection Chart — Line chart (base/upside/stress) + 4.0x ceiling
// ---------------------------------------------------------------------------

export function LeverageProjectionChart({ data, compact = false }: Props) {
  if (!data || data.projections.length === 0) {
    return EMPTY_MSG('Projections not yet run — complete the pipeline to generate.')
  }

  const THRESHOLD = 4.0
  const years = [...new Set(data.projections.map((r) => r.year))].sort((a, b) => a - b)

  const chartData: { group: string; key: string; value: number }[] = []

  for (const year of years) {
    const key = `Y${year}`
    const byScenario = (sc: string) =>
      data.projections.find((r) => r.scenario === sc && r.year === year)?.funded_debt_to_ebitda ?? null

    const base   = byScenario('base')
    const upside = byScenario('upside')
    const stress = byScenario('stress')

    if (base   != null) chartData.push({ group: 'Base Lev.',   key, value: base })
    if (upside != null) chartData.push({ group: 'Upside Lev.', key, value: upside })
    if (stress != null) chartData.push({ group: 'Stress Lev.', key, value: stress })
    chartData.push({ group: '4.0x Max', key, value: THRESHOLD })
  }

  if (chartData.length === 0) return EMPTY_MSG('Leverage data not available in projections.')

  const height = compact ? '90px' : '280px'

  const options = {
    title: compact ? '' : 'Leverage Projection — Funded Debt / EBITDA',
    axes: {
      left: {
        mapsTo: 'value',
        title: compact ? '' : 'Debt/EBITDA (x)',
        ticks: { formatter: (v: number | Date) => `${(v as number).toFixed(1)}x` },
      },
      bottom: {
        mapsTo: 'key',
        scaleType: ScaleTypes.LABELS,
        title: compact ? '' : 'Projection Year',
      },
    },
    color: {
      scale: {
        'Base Lev.':   '#0f62fe',
        'Upside Lev.': '#198038',
        'Stress Lev.': '#da1e28',
        '4.0x Max':    '#f1c21b',
      },
    },
    curve: 'curveMonotoneX',
    height,
    toolbar: { enabled: false },
    legend: { enabled: !compact },
  }

  return (
    <div className={`border border-[#e0e0e0] rounded overflow-hidden ${compact ? '' : 'mt-3'}`}>
      {!compact && (
        <div className="px-3 pt-2 pb-1 bg-[#f4f4f4] border-b border-[#e0e0e0]">
          <p className="text-[10px] text-[#6f6f6f]">
            Blue = Base · Green = Upside · Red = Stress · Yellow dashed = 4.0x covenant ceiling
          </p>
        </div>
      )}
      <LineChart data={chartData} options={options} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Revenue & EBITDA Projection Chart — Grouped Bar (base scenario only)
// ---------------------------------------------------------------------------

export function RevenueEbitdaProjectionChart({ data }: Props) {
  if (!data || data.projections.length === 0) {
    return EMPTY_MSG('Projections not yet run — complete the pipeline to generate.')
  }

  const base = data.projections
    .filter((r) => r.scenario === 'base')
    .sort((a, b) => a.year - b.year)

  if (base.length === 0) return EMPTY_MSG('Base scenario not available in projections.')

  const chartData: { group: string; key: string; value: number }[] = []
  for (const row of base) {
    chartData.push({ group: 'Revenue',  key: `Y${row.year}`, value: row.revenue })
    chartData.push({ group: 'EBITDA',   key: `Y${row.year}`, value: row.ebitda })
  }

  const options = {
    title: 'Revenue & EBITDA Projection — Base Scenario',
    axes: {
      left: {
        mapsTo: 'value',
        title: 'Amount',
        ticks: { formatter: (v: number | Date) => scaledLabel(v as number) },
      },
      bottom: {
        mapsTo: 'key',
        scaleType: ScaleTypes.LABELS,
        title: 'Projection Year',
      },
    },
    color: {
      scale: { Revenue: '#0f62fe', EBITDA: '#198038' },
    },
    height: '280px',
    toolbar: { enabled: false },
  }

  return (
    <div className="mt-3 border border-[#e0e0e0] rounded overflow-hidden">
      <div className="px-3 pt-2 pb-1 bg-[#f4f4f4] border-b border-[#e0e0e0]">
        <p className="text-[10px] text-[#6f6f6f]">
          Base scenario only · Blue = Projected Revenue · Green = Projected EBITDA
        </p>
      </div>
      <GroupedBarChart data={chartData} options={options} />
    </div>
  )
}
