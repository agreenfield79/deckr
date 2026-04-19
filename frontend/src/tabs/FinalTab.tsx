import { useState, useEffect, useCallback, useRef } from 'react'
import { Download, FileText, Loader2 } from 'lucide-react'
import * as deckApi from '../api/deck'
import * as slacrApi from '../api/slacr'
import { getExtractedFinancials } from '../api/financials'
import type { ExtractedFinancials, RatioRow, CovenantRow } from '../api/financials'
import { getRatios, getCovenants } from '../api/financials'
import type { SlacrOutput } from '../types/slacr'
import MarkdownViewer from '../editor/MarkdownViewer'
import { RevenueEbitdaChart, LeverageChart, SlacrRadarChart } from '../charts/FinancialCharts'
import { DscrProjectionChart, LeverageProjectionChart, RevenueEbitdaProjectionChart } from '../charts/ProjectionsChart'
import { getProjectionsOutput, type ProjectionsOutput } from '../api/projections'
import { getCurrentDeal } from '../api/pipelineRuns'
import { useToast } from '../context/ToastContext'

function parseSections(markdown: string): Record<string, string> {
  const sections: Record<string, string> = {}
  // Normalize line endings; accept one or more newlines between heading and content.
  // Agents output single \n between heading and body — \n\n is not guaranteed.
  const normalized = markdown.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const regex = /## \d+\. (.+?)\n+([\s\S]*?)(?=\n---|\n## \d+\.|$)/g
  let match
  while ((match = regex.exec(normalized)) !== null) {
    const name = match[1].trim()
    const content = match[2].trim()
    sections[name] = content
  }
  return sections
}

export default function FinalTab() {
  const { error: toastError } = useToast()
  const finalRef = useRef<HTMLDivElement>(null)

  const [sections, setSections] = useState<Record<string, string>>({})
  const [slacrData, setSlacrData] = useState<SlacrOutput | null>(null)
  const [financials, setFinancials] = useState<ExtractedFinancials | null>(null)
  const [projectionsData, setProjectionsData] = useState<ProjectionsOutput | null>(null)
  const [ratios, setRatios] = useState<RatioRow[]>([])
  const [covenants, setCovenants] = useState<CovenantRow[]>([])
  const [loading, setLoading] = useState(true)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      await Promise.all([
        deckApi.getDeck().then((res) => {
          if (res.exists && res.content) setSections(parseSections(res.content))
        }),
        slacrApi.getScore().then(setSlacrData).catch(() => {}),
        getExtractedFinancials().then(setFinancials).catch(() => {}),
        getCurrentDeal().then(async (deal) => {
          if (deal.deal_id) {
            await Promise.all([
              getProjectionsOutput(deal.deal_id).then((p) => {
                if (p) setProjectionsData(p)
              }).catch(() => {}),
              getRatios(deal.deal_id).then(setRatios).catch(() => {}),
              getCovenants(deal.deal_id).then(setCovenants).catch(() => {}),
            ])
          }
        }).catch(() => {}),
      ])
    } catch {
      toastError('Failed to load final document')
    } finally {
      setLoading(false)
    }
  }, [toastError])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  const handleDownloadPdf = () => {
    const el = finalRef.current
    if (!el) return

    // Clone the fully-rendered DOM (Carbon Charts SVGs included) onto body,
    // bypassing the overflow-y-auto scroll container that clips the content
    // to one page when window.print() is called directly on the nested element.
    const clone = el.cloneNode(true) as HTMLElement
    clone.id = 'print-portal'
    document.body.appendChild(clone)

    // Inject a print rule that hides the app and shows only the clone.
    const style = document.createElement('style')
    style.id = 'print-portal-style'
    style.textContent = `
      @media print {
        @page { size: letter portrait; margin: 0.65in 0.75in; }
        body > *:not(#print-portal) { display: none !important; }
        #print-portal {
          display: block !important;
          width: 100% !important;
          max-width: none !important;
          margin: 0 !important;
          padding: 0 !important;
          border: none !important;
          background: white !important;
        }
        #print-portal h2, #print-portal table { break-inside: avoid; }
      }
    `
    document.head.appendChild(style)

    // Clean up after the print dialog closes (print or cancel).
    const cleanup = () => {
      document.body.removeChild(clone)
      document.head.removeChild(style)
      window.removeEventListener('afterprint', cleanup)
    }
    window.addEventListener('afterprint', cleanup)

    window.print()
  }

  const sectionEntries = Object.entries(sections)
  const completedCount = sectionEntries.filter(
    ([, content]) => content && !content.startsWith('> **PENDING**'),
  ).length

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={20} className="animate-spin text-[#0f62fe]" />
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Toolbar — hidden when printing */}
      <div className="no-print flex items-center justify-between px-4 py-2 border-b border-[#e0e0e0] bg-[#f4f4f4] shrink-0">
        <div className="flex items-center gap-2">
          <FileText size={13} className="text-[#525252]" />
          <span className="text-xs font-semibold text-[#525252] uppercase tracking-wider">
            Final Document
          </span>
          <span className="text-[10px] text-[#6f6f6f] bg-[#e0e0e0] px-1.5 py-0.5 rounded font-mono">
            {completedCount}/{sectionEntries.length} sections
          </span>
        </div>
        <button
          onClick={handleDownloadPdf}
          title="Print or save as PDF"
          className="flex items-center gap-1 px-2 py-1 text-xs text-white bg-[#0f62fe] hover:bg-[#0043ce] rounded transition-colors"
        >
          <Download size={11} />
          Save as PDF
        </button>
      </div>

      {/* Document scroll area */}
      <div className="flex-1 overflow-y-auto bg-[#f4f4f4] py-6 px-4">
        {/* Letter-width document container */}
        <div
          id="final-credit-memo"
          ref={finalRef}
          className="mx-auto bg-white border border-[#e0e0e0]"
          style={{ maxWidth: '768px', padding: '48px 64px', minHeight: '1056px' }}
        >
          {/* Document header */}
          <div className="border-b-2 border-[#0f62fe] pb-4 mb-8">
            <p className="text-[10px] text-[#6f6f6f] uppercase tracking-widest font-semibold mb-1">
              Confidential
            </p>
            <h1 className="text-2xl font-bold text-[#161616] tracking-tight">
              Credit Memorandum
            </h1>
            <p className="text-xs text-[#525252] mt-1">
              Generated {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
            </p>
          </div>

          {/* Sections */}
          {sectionEntries.map(([name, content], idx) => {
            const isPending = !content || content.startsWith('> **PENDING**')

            return (
              <div key={name} className="mb-8">
                <h2 className="text-base font-bold text-[#161616] mb-3 pb-1 border-b border-[#e0e0e0]">
                  {idx + 1}. {name}
                </h2>

                {isPending ? (
                  <p className="text-xs text-[#a8a8a8] italic">
                    [Section pending — run agents to generate]
                  </p>
                ) : (
                  <div className="text-sm">
                    <MarkdownViewer content={content} />
                  </div>
                )}

                {/* Inline charts after relevant sections */}
                {name.includes('Financial Analysis') && (
                  <>
                    <RevenueEbitdaChart data={financials} />
                    {ratios.length > 0 && <RatioDashboardInline ratios={ratios} />}
                  </>
                )}
                {(name === 'Leverage' || name.includes('Leverage & Capitalization')) && (
                  <LeverageChart data={financials} />
                )}
                {(name === 'SLACR Score' || name.includes('SLACR Risk Rating')) && slacrData && (
                  <SlacrRadarChart data={slacrData} />
                )}
                {/* Covenant table after covenant / risk section */}
                {(name.includes('Covenant') || name.includes('Risk Rating')) && covenants.length > 0 && (
                  <CovenantTableInline covenants={covenants} />
                )}
                {/* Projections section: inject all three projection charts for print */}
                {(name.includes('Covenant Compliance') || name.includes('Financial Projections')) && (
                  <>
                    <DscrProjectionChart data={projectionsData} />
                    <LeverageProjectionChart data={projectionsData} />
                    <RevenueEbitdaProjectionChart data={projectionsData} />
                  </>
                )}
              </div>
            )
          })}

          {/* Footer */}
          <div className="border-t border-[#e0e0e0] mt-8 pt-4">
            <p className="text-[10px] text-[#a8a8a8] text-center">
              Generated by Deckr · Powered by IBM watsonx · Confidential and Proprietary
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Print-optimized inline table components
// ---------------------------------------------------------------------------

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`
  return `${sign}$${abs.toFixed(0)}`
}

function RatioDashboardInline({ ratios }: { ratios: RatioRow[] }) {
  return (
    <div className="mt-3 mb-2" style={{ pageBreakInside: 'avoid' }}>
      <p className="text-[10px] font-semibold text-[#525252] uppercase tracking-wider mb-1.5">
        Historical Financial Ratios
      </p>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="bg-[#f4f4f4]">
            <th className="text-left py-1.5 px-2 border border-[#e0e0e0] font-semibold text-[#161616]">Metric</th>
            {ratios.map((r) => (
              <th key={r.fiscal_year} className="text-right py-1.5 px-2 border border-[#e0e0e0] font-semibold text-[#161616]">
                {r.fiscal_year}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {([
            { label: 'DSCR',               key: 'historical_dscr' as const,        threshold: 1.25, higherBetter: true },
            { label: 'Fixed Charge Cov.',  key: 'fixed_charge_coverage' as const,  threshold: 1.25, higherBetter: true },
            { label: 'Leverage Ratio',     key: 'leverage_ratio' as const,         threshold: 4,    higherBetter: false },
            { label: 'Funded Debt/EBITDA', key: 'funded_debt_to_ebitda' as const,  threshold: 4,    higherBetter: false },
            { label: 'Current Ratio',      key: 'current_ratio' as const,          threshold: 1.0,  higherBetter: true },
            { label: 'EBITDA Margin',      key: 'ebitda_margin' as const,          threshold: null, higherBetter: true },
          ]).map(({ label, key, threshold, higherBetter }) => (
            <tr key={key} className="hover:bg-[#f9f9f9]">
              <td className="py-1.5 px-2 text-[#525252] border border-[#e0e0e0]">{label}</td>
              {ratios.map((r) => {
                const v = r[key]
                let color = '#161616'
                if (v != null && threshold != null) {
                  const pass = higherBetter ? v >= threshold : v <= threshold
                  const warn = higherBetter ? v >= threshold * 0.9 : v <= threshold * 1.1
                  color = pass ? '#198038' : warn ? '#b28600' : '#da1e28'
                }
                return (
                  <td key={r.fiscal_year} className="py-1.5 px-2 text-right border border-[#e0e0e0] font-mono"
                    style={{ color }}>
                    {key === 'ebitda_margin' && v != null ? `${(v * 100).toFixed(1)}%` : v != null ? v.toFixed(2) : '—'}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CovenantTableInline({ covenants }: { covenants: CovenantRow[] }) {
  return (
    <div className="mt-3 mb-2" style={{ pageBreakInside: 'avoid' }}>
      <p className="text-[10px] font-semibold text-[#525252] uppercase tracking-wider mb-1.5">
        Covenant Compliance
      </p>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="bg-[#f4f4f4]">
            {['Metric', 'Threshold', 'Actual', 'Status', 'Agent'].map((h) => (
              <th key={h} className="text-left py-1.5 px-2 border border-[#e0e0e0] font-semibold text-[#161616]">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {covenants.map((c, i) => {
            const pass = c.pass_fail === true || c.pass_fail === 'true' || (c.pass_fail as unknown) === 1
            return (
              <tr key={i} className="hover:bg-[#f9f9f9]">
                <td className="py-1.5 px-2 text-[#161616] border border-[#e0e0e0]">
                  {c.metric}
                  {c.description && <span className="text-[#8d8d8d] ml-1">— {c.description}</span>}
                </td>
                <td className="py-1.5 px-2 text-right text-[#525252] border border-[#e0e0e0] font-mono">
                  {c.threshold_value != null ? c.threshold_value.toFixed(2) : '—'}
                </td>
                <td className="py-1.5 px-2 text-right text-[#161616] border border-[#e0e0e0] font-mono">
                  {c.actual_value != null ? c.actual_value.toFixed(2) : '—'}
                </td>
                <td className="py-1.5 px-2 text-center border border-[#e0e0e0]">
                  <span style={{ color: pass ? '#198038' : '#da1e28', fontWeight: 600 }}>
                    {pass ? '✓ Pass' : '✗ Fail'}
                  </span>
                </td>
                <td className="py-1.5 px-2 text-[#8d8d8d] border border-[#e0e0e0]">
                  {c.source_agent ?? '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
