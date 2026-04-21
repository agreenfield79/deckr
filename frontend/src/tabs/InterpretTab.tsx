import { useState, useEffect, useCallback, useRef } from 'react'
import { Brain, ChevronDown, ChevronRight, Loader2, Printer, BarChart2 } from 'lucide-react'
import * as interpretApi from '../api/interpret'
import type { NeuralSlacrOutput } from '../api/interpret'
import { getFile } from '../api/workspace'
import { get } from '../api/client'
import { getCurrentDeal } from '../api/pipelineRuns'
import MarkdownViewer from '../editor/MarkdownViewer'
import {
  ShapWaterfallChart,
  ScoreDistributionChart,
  CorrelationHeatmapChart,
  SlacrRadarChart,
} from '../charts/FinancialCharts'
import SlacrWorksheet from './SlacrWorksheet'
import { useSession } from '../hooks/useSession'
import { useToast } from '../context/ToastContext'
import { useProject } from '../context/ProjectContext'
import type { SlacrOutput } from '../types/slacr'
import FinancialSummaryGrid from '../components/FinancialSummaryGrid'
import LimeExplanationChart from '../components/LimeExplanationChart'
import RiskScoreGauge from '../components/RiskScoreGauge'
import DealGraph from '../components/DealGraph'
import ExternalNetworkGraph from '../components/ExternalNetworkGraph'
import AgentWordCloud from '../components/AgentWordCloud'
import { getFinancialSummary, getShapLime } from '../api/financials'
import type { FinancialSummaryResponse, ShapLimeResponse } from '../api/financials'

const NARRATIVE_PATH = 'Agent Notes/neural_slacr.md'

interface RatioRow {
  fiscal_year: number
  historical_dscr: number | null
  leverage_ratio: number | null
  current_ratio: number | null
  ebitda_margin: number | null
  funded_debt_to_ebitda: number | null
}

/** Convert NeuralSlacrOutput input_values to a minimal SlacrOutput for the radar chart. */
function toSlacrOutput(data: NeuralSlacrOutput): SlacrOutput {
  return {
    input: {
      strength:        data.input_values['Strength']        ?? 3,
      leverage:        data.input_values['Leverage']        ?? 3,
      ability_to_repay: data.input_values['Ability to Repay'] ?? 3,
      collateral:      data.input_values['Collateral']      ?? 3,
      risk_factors:    data.input_values['Risk Factors']    ?? 3,
      notes:           {},
    },
    weighted_score: data.composite_score,
    rating:         data.predicted_rating,
    decision:       '',
    mitigants:      [],
    ai_narrative:   '',
  }
}

const RATING_COLOR: Record<string, string> = {
  'Low Risk':      '#24a148',
  'Moderate Risk': '#0f62fe',
  'Elevated Risk': '#f1c21b',
  'High Risk':     '#ff832b',
  'Decline':       '#da1e28',
}

export default function InterpretTab() {
  const { sessionId } = useSession()
  const { refreshTree } = useProject()
  const { success: toastSuccess, error: toastError } = useToast()
  const printRef = useRef<HTMLDivElement>(null)

  const [modelOutput, setModelOutput] = useState<NeuralSlacrOutput | null>(null)
  const [narrative, setNarrative] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [loadingInit, setLoadingInit] = useState(true)
  const [overrideOpen, setOverrideOpen] = useState(false)

  // Ratio dashboard state
  const [ratios, setRatios]           = useState<RatioRow[]>([])
  const [ratiosOpen, setRatiosOpen]   = useState(true)
  // Financial summary grid state
  const [financialSummary, setFinancialSummary] = useState<FinancialSummaryResponse | null>(null)
  const [summaryOpen, setSummaryOpen] = useState(false)
  // SHAP/LIME from SQL state
  const [shapLime, setShapLime] = useState<ShapLimeResponse | null>(null)

  // -------------------------------------------------------------------------
  // On mount: restore last-run results without re-triggering the model
  // -------------------------------------------------------------------------
  const fetchLastRun = useCallback(async () => {
    setLoadingInit(true)
    try {
      const output = await interpretApi.getNeuralSlacrOutput()
      setModelOutput(output)
    } catch {
      // 404 means never run yet — not an error
    }
    try {
      const res = await getFile(NARRATIVE_PATH)
      if (res.content) setNarrative(res.content)
    } catch {
      // narrative not yet generated
    }
    // Load SQL ratio dashboard
    try {
      const deal = await getCurrentDeal()
      if (deal.deal_id) {
        const ratioRes = await get<{ ratios: RatioRow[] }>(`/financials/ratios/${deal.deal_id}`)
        setRatios(ratioRes.ratios ?? [])

        // Financial summary
        getFinancialSummary(deal.deal_id).then((s) => {
          if (s) setFinancialSummary(s)
        }).catch(() => {})

        // SHAP/LIME from SQL
        getShapLime(deal.deal_id).then((s) => {
          if (s) setShapLime(s)
        }).catch(() => {})
      }
    } catch {
      // Ratios not yet available — not an error
    }
    setLoadingInit(false)
  }, [])

  useEffect(() => {
    fetchLastRun()
  }, [fetchLastRun])

  // -------------------------------------------------------------------------
  // Run Interpreter
  // -------------------------------------------------------------------------
  const handleRunInterpreter = async () => {
    setRunning(true)
    try {
      const output = await interpretApi.postRunInterpreter(sessionId)
      setModelOutput(output)
      toastSuccess(
        `Neural SLACR: ${output.predicted_rating} (${(output.probability * 100).toFixed(1)}% confidence)`,
      )
      // Reload narrative saved by the interpreter agent
      try {
        const res = await getFile(NARRATIVE_PATH)
        if (res.content) setNarrative(res.content)
      } catch {
        // Narrative best-effort — charts still render
      }
      await refreshTree()
    } catch (err) {
      toastError('Interpreter failed — check backend logs')
      console.error(err)
    } finally {
      setRunning(false)
    }
  }

  // -------------------------------------------------------------------------
  // Print portal
  // -------------------------------------------------------------------------
  const handlePrint = () => {
    const el = printRef.current
    if (!el) return

    const clone = el.cloneNode(true) as HTMLElement
    clone.id = 'print-portal'
    document.body.appendChild(clone)

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
        #print-portal canvas { max-width: 100% !important; }
      }
    `
    document.head.appendChild(style)

    const cleanup = () => {
      document.body.removeChild(clone)
      document.head.removeChild(style)
      window.removeEventListener('afterprint', cleanup)
    }
    window.addEventListener('afterprint', cleanup)
    window.print()
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  const ratingColor = modelOutput
    ? (RATING_COLOR[modelOutput.predicted_rating] ?? '#525252')
    : '#525252'

  if (loadingInit) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={20} className="animate-spin text-[#6929c4]" />
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="no-print flex items-center justify-between px-4 py-2 border-b border-[#e0e0e0] bg-[#f4f4f4] shrink-0">
        <div className="flex items-center gap-2">
          <Brain size={13} className="text-[#6929c4]" />
          <span className="text-xs font-semibold text-[#525252] uppercase tracking-wider">
            Neural SLACR Interpreter
          </span>
          {modelOutput && (
            <span
              className="text-[10px] font-semibold px-2 py-0.5 rounded"
              style={{ color: ratingColor, backgroundColor: `${ratingColor}18` }}
            >
              {modelOutput.predicted_rating} — {(modelOutput.probability * 100).toFixed(1)}%
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRunInterpreter}
            disabled={running}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-[#6929c4] hover:bg-[#491d8b] rounded transition-colors disabled:opacity-50"
          >
            {running ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Brain size={12} />
            )}
            {running ? 'Running…' : 'Run Interpreter'}
          </button>
          {modelOutput && (
            <button
              onClick={handlePrint}
              title="Print or save as PDF"
              className="flex items-center gap-1 px-2 py-1 text-xs text-[#525252] bg-white border border-[#e0e0e0] hover:bg-[#e8e8e8] rounded transition-colors"
            >
              <Printer size={11} />
              Print
            </button>
          )}
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        <div ref={printRef} className="max-w-4xl mx-auto px-5 py-5 space-y-6">

          {/* Empty state */}
          {!modelOutput && !running && (
            <div className="flex flex-col items-center justify-center py-16 gap-4">
              <Brain size={40} className="text-[#6929c4] opacity-40" />
              <div className="text-center max-w-sm">
                <p className="text-sm font-semibold text-[#161616] mb-1">
                  Neural SLACR not yet run
                </p>
                <p className="text-xs text-[#6f6f6f] leading-relaxed">
                  Score the SLACR dimensions below, then click "Run Interpreter" to generate
                  ML predictions, SHAP values, LIME explanations, and an AI narrative.
                </p>
              </div>
            </div>
          )}

          {/* Running state */}
          {running && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 size={28} className="animate-spin text-[#6929c4]" />
              <p className="text-xs text-[#525252]">
                Running Neural SLACR model + Interpreter Agent…
              </p>
            </div>
          )}

          {/* Results */}
          {modelOutput && !running && (
            <>
              {/* Prediction summary card — with Risk Score Gauge */}
              <div
                className="rounded-lg border-2 p-4 flex items-center justify-between gap-4"
                style={{ borderColor: ratingColor, backgroundColor: `${ratingColor}10` }}
              >
                <div className="flex-1">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[#525252]">
                    ML Predicted Rating
                  </p>
                  <p className="text-3xl font-bold mt-0.5" style={{ color: ratingColor }}>
                    {modelOutput.predicted_rating}
                  </p>
                  <p className="text-xs text-[#525252] mt-1">
                    Confidence: {(modelOutput.probability * 100).toFixed(1)}%
                  </p>
                </div>
                <RiskScoreGauge
                  score={modelOutput.composite_score}
                  rating={modelOutput.predicted_rating}
                  size={120}
                />
                <div className="text-right space-y-1">
                  <div>
                    <p className="text-[10px] font-semibold text-[#525252] uppercase tracking-wider">
                      SLACR Composite
                    </p>
                    <p className="text-xl font-bold text-[#161616]">
                      {modelOutput.composite_score.toFixed(2)}
                    </p>
                  </div>
                  <div className="text-[10px] text-[#6f6f6f]">
                    Analyst-scored weighted average
                  </div>
                </div>
              </div>

              {/* Charts — 2-column grid */}
              <div>
                <h3 className="text-xs font-semibold text-[#161616] uppercase tracking-wider mb-3">
                  Explainability Charts
                </h3>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <div>
                    <p className="text-[11px] font-medium text-[#525252] mb-1">
                      SHAP Feature Contributions
                    </p>
                    <ShapWaterfallChart data={modelOutput} />
                  </div>
                  <div>
                    <p className="text-[11px] font-medium text-[#525252] mb-1">
                      LIME Local Explanation
                    </p>
                    {shapLime?.lime_values ? (
                      <LimeExplanationChart limeValues={shapLime.lime_values} />
                    ) : (
                      <div>
                        <p className="text-[11px] font-medium text-[#525252] mb-1">
                          SLACR Risk Profile (Analyst Scores)
                        </p>
                        <SlacrRadarChart data={toSlacrOutput(modelOutput)} />
                      </div>
                    )}
                  </div>
                  <div>
                    <p className="text-[11px] font-medium text-[#525252] mb-1">
                      Score Distribution (Training Set)
                    </p>
                    <ScoreDistributionChart data={modelOutput} />
                  </div>
                  <div>
                    <p className="text-[11px] font-medium text-[#525252] mb-1">
                      SLACR Risk Profile (Analyst Scores)
                    </p>
                    <SlacrRadarChart data={toSlacrOutput(modelOutput)} />
                  </div>
                  <div>
                    <p className="text-[11px] font-medium text-[#525252] mb-1">
                      Feature Correlation Matrix
                    </p>
                    <CorrelationHeatmapChart data={modelOutput} />
                  </div>
                </div>
              </div>

              {/* Feature Importances table */}
              <div>
                <h3 className="text-xs font-semibold text-[#161616] uppercase tracking-wider mb-2">
                  Global Feature Importances (Random Forest)
                </h3>
                <div className="border border-[#e0e0e0] rounded overflow-hidden">
                  {modelOutput.feature_importances.map((item, i) => (
                    <div
                      key={item.feature}
                      className="flex items-center px-3 py-2 gap-3 text-xs border-b border-[#e0e0e0] last:border-b-0"
                      style={{ backgroundColor: i % 2 === 0 ? '#f4f4f4' : 'white' }}
                    >
                      <span className="w-5 text-right text-[10px] text-[#6f6f6f] font-mono shrink-0">
                        {i + 1}
                      </span>
                      <span className="flex-1 font-medium text-[#161616]">{item.feature}</span>
                      <div className="w-32 bg-[#e0e0e0] rounded-full h-1.5 shrink-0">
                        <div
                          className="h-1.5 rounded-full"
                          style={{
                            width: `${(item.importance * 100 / modelOutput.feature_importances[0].importance).toFixed(0)}%`,
                            backgroundColor: '#6929c4',
                          }}
                        />
                      </div>
                      <span className="w-12 text-right text-[10px] font-mono text-[#525252] shrink-0">
                        {(item.importance * 100).toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* AI Narrative */}
              {narrative && (
                <div>
                  <h3 className="text-xs font-semibold text-[#161616] uppercase tracking-wider mb-2">
                    AI Interpretation Narrative
                  </h3>
                  <div className="border border-[#e0e0e0] rounded p-4 bg-white text-sm">
                    <MarkdownViewer content={narrative} />
                  </div>
                </div>
              )}
            </>
          )}

          {/* Manual Score Override — collapsible SlacrWorksheet */}
          <div className="border border-[#e0e0e0] rounded-lg overflow-hidden">
            <button
              className="w-full flex items-center justify-between px-4 py-2.5 bg-[#f4f4f4] hover:bg-[#e8e8e8] text-xs font-medium text-[#525252] transition-colors"
              onClick={() => setOverrideOpen(!overrideOpen)}
            >
              <span className="flex items-center gap-2">
                <Brain size={12} className="text-[#6929c4]" />
                Manual Score Override — SLACR Worksheet
              </span>
              {overrideOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            </button>
            {overrideOpen && (
              <div className="border-t border-[#e0e0e0]">
                <SlacrWorksheet />
              </div>
            )}
          </div>

          {/* SQL Ratio Dashboard */}
          <div className="border border-[#e0e0e0] rounded-lg overflow-hidden">
            <button
              className="w-full flex items-center justify-between px-4 py-2.5 bg-[#f4f4f4] hover:bg-[#e8e8e8] text-xs font-medium text-[#525252] transition-colors"
              onClick={() => setRatiosOpen(!ratiosOpen)}
            >
              <span className="flex items-center gap-2">
                <BarChart2 size={12} className="text-[#0f62fe]" />
                SQL Ratio Dashboard
                {ratios.length > 0 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#e0e0e0] text-[#525252]">
                    {ratios.length} year{ratios.length !== 1 ? 's' : ''}
                  </span>
                )}
              </span>
              {ratiosOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            </button>
            {ratiosOpen && (
              <div className="border-t border-[#e0e0e0]">
                {ratios.length === 0 ? (
                  <p className="px-4 py-3 text-xs text-[#6f6f6f] italic">
                    No ratios available — run the pipeline to populate SQL financial ratios.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-[#f4f4f4] text-[10px] text-[#525252] uppercase tracking-wider">
                          <th className="text-left px-3 py-1.5 font-semibold">FY</th>
                          <th className="text-right px-3 py-1.5 font-semibold">DSCR</th>
                          <th className="text-right px-3 py-1.5 font-semibold">Leverage</th>
                          <th className="text-right px-3 py-1.5 font-semibold">Current</th>
                          <th className="text-right px-3 py-1.5 font-semibold">EBITDA Margin</th>
                          <th className="text-right px-3 py-1.5 font-semibold">Debt/EBITDA</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ratios.map((r, i) => {
                          const dscrOk = r.historical_dscr !== null && r.historical_dscr >= 1.25
                          const levOk  = r.leverage_ratio !== null && r.leverage_ratio <= 5.0
                          const curOk  = r.current_ratio !== null && r.current_ratio >= 1.0
                          return (
                            <tr key={r.fiscal_year} className={`border-t border-[#f4f4f4] ${i % 2 === 0 ? 'bg-white' : 'bg-[#f9f9f9]'}`}>
                              <td className="px-3 py-1.5 font-mono font-semibold text-[#161616]">
                                FY{r.fiscal_year}
                              </td>
                              <td className={`px-3 py-1.5 text-right font-mono ${r.historical_dscr === null ? 'text-[#a8a8a8]' : dscrOk ? 'text-[#24a148]' : 'text-[#da1e28]'}`}>
                                {r.historical_dscr !== null ? r.historical_dscr.toFixed(2) + 'x' : '—'}
                              </td>
                              <td className={`px-3 py-1.5 text-right font-mono ${r.leverage_ratio === null ? 'text-[#a8a8a8]' : levOk ? 'text-[#24a148]' : 'text-[#da1e28]'}`}>
                                {r.leverage_ratio !== null ? r.leverage_ratio.toFixed(2) + 'x' : '—'}
                              </td>
                              <td className={`px-3 py-1.5 text-right font-mono ${r.current_ratio === null ? 'text-[#a8a8a8]' : curOk ? 'text-[#24a148]' : 'text-[#da1e28]'}`}>
                                {r.current_ratio !== null ? r.current_ratio.toFixed(2) + 'x' : '—'}
                              </td>
                              <td className="px-3 py-1.5 text-right font-mono text-[#525252]">
                                {r.ebitda_margin !== null ? (r.ebitda_margin * 100).toFixed(1) + '%' : '—'}
                              </td>
                              <td className="px-3 py-1.5 text-right font-mono text-[#525252]">
                                {r.funded_debt_to_ebitda !== null ? r.funded_debt_to_ebitda.toFixed(2) + 'x' : '—'}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                    <p className="px-3 py-1.5 text-[10px] text-[#8d8d8d] border-t border-[#f4f4f4]">
                      Green = covenant pass (DSCR ≥ 1.25x · Leverage ≤ 5.0x · Current ≥ 1.0x) · Source: SQL financial_ratios
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Financial Summary Grid — 3-year side-by-side from SQL */}
          <div className="border border-[#e0e0e0] rounded-lg overflow-hidden">
            <button
              className="w-full flex items-center justify-between px-4 py-2.5 bg-[#f4f4f4] hover:bg-[#e8e8e8] text-xs font-medium text-[#525252] transition-colors"
              onClick={() => setSummaryOpen(!summaryOpen)}
            >
              <span className="flex items-center gap-2">
                <BarChart2 size={12} className="text-[#007d79]" />
                Financial Summary (3-Year)
              </span>
              {summaryOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            </button>
            {summaryOpen && (
              <div className="border-t border-[#e0e0e0] px-4 pb-4">
                <FinancialSummaryGrid data={financialSummary} />
              </div>
            )}
          </div>

          {/* External Evidence Word Cloud */}
          <div>
            <h3 className="text-xs font-semibold text-[#161616] uppercase tracking-wider mb-2">
              External Evidence Word Cloud
            </h3>
            <AgentWordCloud />
          </div>

          {/* Deal Structure Graphs */}
          <div>
            <h3 className="text-xs font-semibold text-[#161616] uppercase tracking-wider mb-2">
              Deal Structure Graph
            </h3>
            <DealGraph />
            <ExternalNetworkGraph />
          </div>

        </div>
      </div>
    </div>
  )
}
