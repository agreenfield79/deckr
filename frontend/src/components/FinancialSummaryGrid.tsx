/**
 * FinancialSummaryGrid — 3-year side-by-side income statement + balance sheet + cash flow.
 * Sourced from GET /api/financials/summary?deal_id=
 */

import type { FinancialSummaryResponse, FinancialSummaryRow, CashFlowSummaryRow, BalanceSummaryRow } from '../api/financials'

interface Props {
  data: FinancialSummaryResponse | null
}

function fmt(v: number | null | undefined, prefix = '$'): string {
  if (v == null) return '—'
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1e9) return `${sign}${prefix}${(abs / 1e9).toFixed(1)}B`
  if (abs >= 1e6) return `${sign}${prefix}${(abs / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `${sign}${prefix}${(abs / 1e3).toFixed(0)}K`
  return `${sign}${prefix}${abs.toFixed(0)}`
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function delta(rows: FinancialSummaryRow[], key: keyof FinancialSummaryRow, idx: number): React.ReactNode {
  if (idx === 0) return null
  const curr = rows[idx][key] as number | null
  const prev = rows[idx - 1][key] as number | null
  if (curr == null || prev == null || prev === 0) return null
  const pct = ((curr - prev) / Math.abs(prev)) * 100
  const up = pct >= 0
  return (
    <span className={`ml-1 text-[9px] font-medium ${up ? 'text-[#24a148]' : 'text-[#da1e28]'}`}>
      {up ? '▲' : '▼'}{Math.abs(pct).toFixed(1)}%
    </span>
  )
}

const INC_ROWS: { label: string; key: keyof FinancialSummaryRow; pct?: boolean }[] = [
  { label: 'Revenue',           key: 'revenue' },
  { label: 'Gross Profit',      key: 'gross_profit' },
  { label: 'EBITDA',            key: 'ebitda' },
  { label: 'EBIT',              key: 'ebit' },
  { label: 'Net Income',        key: 'net_income' },
  { label: 'Interest Expense',  key: 'interest_expense' },
  { label: 'D&A',               key: 'depreciation_amortization' },
]

const BS_ROWS: { label: string; key: keyof BalanceSummaryRow }[] = [
  { label: 'Total Assets',        key: 'total_assets' },
  { label: 'Current Assets',      key: 'current_assets' },
  { label: 'Cash',                key: 'cash' },
  { label: 'Total Liabilities',   key: 'total_liabilities' },
  { label: 'Current Liabilities', key: 'current_liabilities' },
  { label: 'Long-Term Debt',      key: 'long_term_debt' },
  { label: 'Total Equity',        key: 'total_equity' },
]

const CF_ROWS: { label: string; key: keyof CashFlowSummaryRow }[] = [
  { label: 'Operating Cash Flow', key: 'operating_cash_flow' },
  { label: 'CapEx',               key: 'capex' },
  { label: 'Free Cash Flow',      key: 'free_cash_flow' },
]

import React from 'react'

export default function FinancialSummaryGrid({ data }: Props) {
  if (!data || (!data.income_statement?.length && !data.balance_sheet?.length)) {
    return (
      <p className="text-xs text-[#a8a8a8] italic mt-2">
        Financial summary not yet available — run the pipeline to populate.
      </p>
    )
  }

  const inc = data.income_statement ?? []
  const bs = data.balance_sheet ?? []
  const cf = data.cash_flow ?? []
  const years = inc.map((r) => r.fiscal_year)

  return (
    <div className="mt-3 space-y-4 text-xs">
      {/* Income Statement */}
      {inc.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-[#525252] uppercase tracking-wider mb-1.5">
            Income Statement
          </p>
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-[#f4f4f4]">
                <th className="text-left py-1.5 px-2 font-semibold text-[#161616] border border-[#e0e0e0] w-40">
                  Metric
                </th>
                {years.map((y) => (
                  <th key={y} className="text-right py-1.5 px-2 font-semibold text-[#161616] border border-[#e0e0e0]">
                    {y}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {INC_ROWS.map(({ label, key }) => (
                <tr key={key} className="hover:bg-[#f9f9f9]">
                  <td className="py-1.5 px-2 text-[#525252] border border-[#e0e0e0]">{label}</td>
                  {inc.map((r, i) => (
                    <td key={r.fiscal_year} className="py-1.5 px-2 text-right text-[#161616] border border-[#e0e0e0] font-mono">
                      {fmt(r[key] as number | null)}
                      {delta(inc, key, i)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Balance Sheet — multi-year */}
      {bs.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-[#525252] uppercase tracking-wider mb-1.5">
            Balance Sheet
          </p>
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-[#f4f4f4]">
                <th className="text-left py-1.5 px-2 font-semibold text-[#161616] border border-[#e0e0e0] w-40">
                  Metric
                </th>
                {bs.map((r, i) => (
                  <th key={r.fiscal_year ?? i} className="text-right py-1.5 px-2 font-semibold text-[#161616] border border-[#e0e0e0]">
                    {r.fiscal_year ?? '—'}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {BS_ROWS.map(({ label, key }) => (
                <tr key={key} className="hover:bg-[#f9f9f9]">
                  <td className="py-1.5 px-2 text-[#525252] border border-[#e0e0e0]">{label}</td>
                  {bs.map((r, i) => (
                    <td key={r.fiscal_year ?? i} className="py-1.5 px-2 text-right text-[#161616] border border-[#e0e0e0] font-mono">
                      {fmt(r[key] as number | null)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Cash Flow */}
      {cf.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-[#525252] uppercase tracking-wider mb-1.5">
            Cash Flow Statement
          </p>
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-[#f4f4f4]">
                <th className="text-left py-1.5 px-2 font-semibold text-[#161616] border border-[#e0e0e0] w-40">Metric</th>
                {cf.map((r) => (
                  <th key={r.fiscal_year} className="text-right py-1.5 px-2 font-semibold text-[#161616] border border-[#e0e0e0]">
                    {r.fiscal_year}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CF_ROWS.map(({ label, key }) => (
                <tr key={key} className="hover:bg-[#f9f9f9]">
                  <td className="py-1.5 px-2 text-[#525252] border border-[#e0e0e0]">{label}</td>
                  {cf.map((r) => (
                    <td key={r.fiscal_year} className="py-1.5 px-2 text-right text-[#161616] border border-[#e0e0e0] font-mono">
                      {fmt(r[key] as number | null)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
