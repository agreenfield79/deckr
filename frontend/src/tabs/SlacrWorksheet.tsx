import { useState } from 'react'
import { Play, Save, ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import MarkdownViewer from '../editor/MarkdownViewer'
import { useSlacrScore } from '../hooks/useSlacrScore'
import { useSession } from '../hooks/useSession'
import { useToast } from '../context/ToastContext'
import { useProject } from '../context/ProjectContext'
import {
  SLACR_DIMENSIONS,
  SCORE_LABELS,
  getRatingColor,
} from '../types/slacr'

const GUIDE_CONTENT = `
### Scoring Guide

Each dimension is scored **1–5** where:

| Score | Label | Meaning |
|---|---|---|
| 1 | Excellent | Strong credit quality — meets or exceeds best-practice benchmarks |
| 2 | Good | Above average — minor concerns, well-mitigated |
| 3 | Acceptable | Meets minimum underwriting standards |
| 4 | Weak | Below standard — significant concerns requiring conditions |
| 5 | High Risk | Material risk factor — approval unlikely without restructuring |

### Rating Bands

| Composite Score | Rating | Decision |
|---|---|---|
| 1.00–1.75 | Low Risk | Approve |
| 1.76–2.50 | Moderate Risk | Approve with conditions |
| 2.51–3.25 | Elevated Risk | Further review required |
| 3.26–4.00 | High Risk | Decline or restructure |
| 4.01–5.00 | Decline | Reject |

### Formula

\`Composite = (S×0.20) + (L×0.20) + (A×0.25) + (C×0.15) + (R×0.20)\`
`.trim()

export default function SlacrWorksheet() {
  const { sessionId } = useSession()
  const { refreshTree } = useProject()
  const { success: toastSuccess, error: toastError } = useToast()
  const {
    scores, result, loading, agentRunning,
    liveScore, setScore, setNote, submit, runAgent,
  } = useSlacrScore()

  const [guideOpen, setGuideOpen] = useState(false)

  const handleSave = async () => {
    const output = await submit()
    if (output) {
      await refreshTree()
      toastSuccess(`SLACR scored: ${output.weighted_score.toFixed(2)} — ${output.rating}`)
    } else {
      toastError('Failed to save SLACR score')
    }
  }

  const handleRunAgent = async () => {
    const res = await runAgent(sessionId)
    if (res) {
      await refreshTree()
      toastSuccess('Risk agent analysis saved → SLACR/slacr_analysis.md + SLACR/slacr.json')
    } else {
      toastError('Risk agent run failed')
    }
  }

  const ratingColor = getRatingColor(liveScore)
  const savedRatingColor = result ? getRatingColor(result.weighted_score) : undefined

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-2xl mx-auto px-5 py-5 space-y-5">

        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-[#161616]">SLACR Risk Worksheet</h2>
            <p className="text-xs text-[#6f6f6f] mt-0.5">
              Score five risk dimensions · 1 = Excellent · 5 = High Risk
            </p>
          </div>
          <button
            onClick={handleRunAgent}
            disabled={agentRunning || loading}
            title="Run Risk Agent — analyzes workspace documents and auto-scores all dimensions"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-[#0f62fe] hover:bg-[#0043ce] rounded transition-colors disabled:opacity-50 shrink-0"
          >
            {agentRunning ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Play size={12} />
            )}
            {agentRunning ? 'Running…' : 'Run Risk Agent'}
          </button>
        </div>

        {/* Live Score Panel */}
        <div
          className="rounded-lg border-2 p-4 flex items-center justify-between"
          style={{ borderColor: ratingColor, backgroundColor: `${ratingColor}18` }}
        >
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[#525252]">
              Live Composite Score
            </p>
            <p className="text-3xl font-bold mt-0.5" style={{ color: ratingColor }}>
              {liveScore.toFixed(2)}
            </p>
          </div>
          <div className="text-right">
            <p
              className="text-sm font-semibold"
              style={{ color: ratingColor }}
            >
              {liveScore <= 1.75 ? 'Low Risk' :
               liveScore <= 2.50 ? 'Moderate Risk' :
               liveScore <= 3.25 ? 'Elevated Risk' :
               liveScore <= 4.00 ? 'High Risk' : 'Decline'}
            </p>
            <p className="text-xs text-[#525252] mt-0.5">
              {liveScore <= 1.75 ? 'Approve' :
               liveScore <= 2.50 ? 'Approve with conditions' :
               liveScore <= 3.25 ? 'Further review required' :
               liveScore <= 4.00 ? 'Decline or restructure' : 'Reject'}
            </p>
          </div>
        </div>

        {/* Dimension Sliders */}
        <div className="space-y-4">
          {SLACR_DIMENSIONS.map(({ field, label, weight, description }) => {
            const value = scores[field] as number
            const scoreInfo = SCORE_LABELS[value]
            return (
              <div key={field} className="bg-white border border-[#e0e0e0] rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span className="text-xs font-semibold text-[#161616]">{label}</span>
                    <span className="ml-1.5 text-[10px] text-[#8d8d8d] bg-[#e0e0e0] px-1 rounded font-mono">
                      {weight}
                    </span>
                  </div>
                  <span
                    className="text-xs font-semibold px-2 py-0.5 rounded"
                    style={{ color: scoreInfo.color, backgroundColor: `${scoreInfo.color}18` }}
                  >
                    {value} — {scoreInfo.label}
                  </span>
                </div>
                <p className="text-[10px] text-[#6f6f6f] mb-3">{description}</p>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-[#24a148] font-medium w-16 text-left shrink-0">
                    1 Excellent
                  </span>
                  <input
                    type="range"
                    min={1}
                    max={5}
                    step={1}
                    value={value}
                    onChange={(e) => setScore(field, parseInt(e.target.value))}
                    className="flex-1 accent-[#0f62fe]"
                  />
                  <span className="text-[10px] text-[#da1e28] font-medium w-16 text-right shrink-0">
                    5 High Risk
                  </span>
                </div>
                {/* Tick marks */}
                <div className="flex justify-between px-1 mt-0.5">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <span
                      key={n}
                      className="text-[9px] text-[#a8a8a8]"
                      style={{ color: n === value ? ratingColor : undefined }}
                    >
                      {n}
                    </span>
                  ))}
                </div>
                {/* Analyst notes */}
                <textarea
                  value={scores.notes[label] ?? ''}
                  onChange={(e) => setNote(label, e.target.value)}
                  placeholder="Analyst notes (optional)…"
                  rows={2}
                  className="mt-3 w-full text-xs text-[#161616] border border-[#e0e0e0] rounded px-2.5 py-1.5 bg-[#f4f4f4] resize-none focus:outline-none focus:border-[#0f62fe] focus:bg-white transition-colors placeholder:text-[#a8a8a8]"
                />
              </div>
            )
          })}
        </div>

        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={loading || agentRunning}
          className="w-full flex items-center justify-center gap-2 py-2 text-xs font-semibold text-white bg-[#0f62fe] hover:bg-[#0043ce] rounded transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
          {loading ? 'Saving…' : 'Save Score to SLACR/slacr.json'}
        </button>

        {/* Saved result summary */}
        {result && (
          <div className="border border-[#e0e0e0] rounded-lg overflow-hidden">
            <div
              className="px-4 py-2.5 flex items-center justify-between"
              style={{ backgroundColor: `${savedRatingColor}18` }}
            >
              <span className="text-xs font-semibold text-[#161616]">Last Saved Score</span>
              <span
                className="text-xs font-semibold"
                style={{ color: savedRatingColor }}
              >
                {result.weighted_score.toFixed(2)} — {result.rating}
              </span>
            </div>
            <div className="px-4 py-3 space-y-2 text-xs text-[#161616]">
              <div className="flex gap-6">
                <div>
                  <span className="text-[10px] text-[#6f6f6f] block">Decision</span>
                  <span className="font-medium">{result.decision}</span>
                </div>
              </div>
              {result.mitigants.length > 0 && result.mitigants[0] !== 'Standard monitoring and covenant compliance' && (
                <div>
                  <span className="text-[10px] text-[#6f6f6f] block mb-1">Recommended Conditions</span>
                  <ul className="space-y-0.5">
                    {result.mitigants.map((m, i) => (
                      <li key={i} className="flex gap-1.5 text-xs text-[#525252]">
                        <span className="text-[#0f62fe] shrink-0">·</span>
                        {m}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {result.ai_narrative && (
                <div>
                  <span className="text-[10px] text-[#6f6f6f] block mb-1">AI Narrative</span>
                  <div className="max-h-40 overflow-y-auto border border-[#e0e0e0] rounded p-2 bg-[#f4f4f4]">
                    <MarkdownViewer content={result.ai_narrative} />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Scoring Guide (expandable) */}
        <div className="border border-[#e0e0e0] rounded-lg overflow-hidden">
          <button
            className="w-full flex items-center justify-between px-4 py-2.5 bg-[#f4f4f4] hover:bg-[#e8e8e8] text-xs font-medium text-[#525252] transition-colors"
            onClick={() => setGuideOpen(!guideOpen)}
          >
            View Scoring Guide
            {guideOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
          {guideOpen && (
            <div className="px-4 py-3 text-xs">
              <MarkdownViewer content={GUIDE_CONTENT} />
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
