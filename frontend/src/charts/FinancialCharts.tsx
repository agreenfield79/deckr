import { GroupedBarChart, LineChart, RadarChart } from '@carbon/charts-react'
import { ScaleTypes } from '@carbon/charts'
import type { ExtractedFinancials } from '../api/financials'
import type { SlacrOutput } from '../types/slacr'
import { SLACR_DIMENSIONS } from '../types/slacr'

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

// ---------------------------------------------------------------------------
// Revenue & EBITDA — GroupedBarChart
// ---------------------------------------------------------------------------

interface FinancialChartsProps {
  data: ExtractedFinancials | null
}

export function RevenueEbitdaChart({ data }: FinancialChartsProps) {
  if (!data) return EMPTY_MSG('Financial data not yet extracted.')

  const years = data.fiscal_years ?? []
  const revenue = data.income_statement?.revenue ?? {}
  const ebitda = data.income_statement?.ebitda ?? {}

  const hasRevenue = years.some((y) => revenue[y] != null)
  const hasEbitda = years.some((y) => ebitda[y] != null)

  if (!hasRevenue && !hasEbitda) {
    return EMPTY_MSG('Revenue and EBITDA data not available.')
  }

  const chartData: { group: string; key: string; value: number }[] = []
  for (const year of years) {
    if (revenue[year] != null) {
      chartData.push({ group: 'Revenue', key: year, value: revenue[year] as number })
    }
    if (ebitda[year] != null) {
      chartData.push({ group: 'EBITDA', key: year, value: ebitda[year] as number })
    }
  }

  if (chartData.length === 0) return EMPTY_MSG('Revenue and EBITDA data not available.')

  const options = {
    title: 'Revenue & EBITDA Trend',
    axes: {
      left: {
        mapsTo: 'value',
        title: 'Amount',
        ticks: { formatter: (tick: number | Date) => scaledLabel(tick as number) },
      },
      bottom: {
        mapsTo: 'key',
        scaleType: ScaleTypes.LABELS,
        title: 'Fiscal Year',
      },
    },
    color: {
      scale: { Revenue: '#0f62fe', EBITDA: '#198038' },
    },
    height: '300px',
    toolbar: { enabled: false },
  }

  return (
    <div className="mt-3 border border-[#e0e0e0] rounded overflow-hidden">
      <GroupedBarChart data={chartData} options={options} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Leverage & DSCR — LineChart
// ---------------------------------------------------------------------------

export function LeverageChart({ data }: FinancialChartsProps) {
  if (!data) return EMPTY_MSG('Financial data not yet extracted.')

  const years = data.fiscal_years ?? []
  const totalDebt = data.balance_sheet?.total_debt ?? {}
  const totalEquity = data.balance_sheet?.total_equity ?? {}
  const operatingCF = data.cash_flow_statement?.operating_cash_flow ?? {}
  const interestExp = data.income_statement?.interest_expense ?? {}

  const chartData: { group: string; key: string; value: number }[] = []

  for (const year of years) {
    const debt = totalDebt[year]
    const equity = totalEquity[year]
    if (debt != null && equity != null && equity !== 0) {
      chartData.push({ group: 'D/E Ratio', key: year, value: parseFloat((debt / equity).toFixed(2)) })
    }
    const ocf = operatingCF[year]
    const interest = interestExp[year]
    if (ocf != null && interest != null && interest !== 0) {
      chartData.push({ group: 'DSCR', key: year, value: parseFloat((ocf / interest).toFixed(2)) })
    }
  }

  if (chartData.length === 0) {
    return EMPTY_MSG('Leverage and DSCR data not available (requires debt, equity, and interest expense).')
  }

  const options = {
    title: 'Leverage & Debt Service Coverage',
    axes: {
      left: {
        mapsTo: 'value',
        title: 'Ratio (x)',
      },
      bottom: {
        mapsTo: 'key',
        scaleType: ScaleTypes.LABELS,
        title: 'Fiscal Year',
      },
    },
    color: {
      scale: { 'D/E Ratio': '#da1e28', DSCR: '#0f62fe' },
    },
    height: '280px',
    toolbar: { enabled: false },
  }

  return (
    <div className="mt-3 border border-[#e0e0e0] rounded overflow-hidden">
      <LineChart data={chartData} options={options} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// SLACR Radar Chart
// ---------------------------------------------------------------------------

interface SlacrRadarChartProps {
  data: SlacrOutput | null
}

export function SlacrRadarChart({ data }: SlacrRadarChartProps) {
  if (!data) return EMPTY_MSG('SLACR score not yet computed.')

  // Carbon RadarChart: higher value = better. SLACR scores are 1 (best) → 5 (worst).
  // Invert: inverted = 6 - score so 5=excellent appears large, 1=high risk appears small.
  // "/" in keys breaks D3's internal CSS selector logic — replace with "&".
  const chartData = SLACR_DIMENSIONS.map((dim) => ({
    key: dim.label.replace(/\s*\/\s*/g, ' & '),
    value: 6 - (data.input[dim.field] as number),
  }))

  const options = {
    title: 'SLACR Risk Profile',
    radar: {
      axes: { angle: 'key', value: 'value' },
    },
    color: {
      scale: { value: '#0f62fe' },
    },
    height: '320px',
    toolbar: { enabled: false },
  }

  return (
    <div className="mt-4 border border-[#e0e0e0] rounded overflow-hidden">
      <div className="px-3 pt-2 pb-1 bg-[#f4f4f4] border-b border-[#e0e0e0]">
        <p className="text-[10px] text-[#6f6f6f]">
          Outer = lower risk · Inner = higher risk · Scale inverted for visual clarity (1=High Risk, 5=Excellent)
        </p>
      </div>
      <RadarChart data={chartData} options={options} />
    </div>
  )
}
