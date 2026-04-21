/**
 * PipelineGantt — horizontal Gantt chart for pipeline run stages.
 * Sources from GET /api/mongo/pipeline-timeline
 * Pure SVG/React — no D3 required for this level of complexity.
 */

import { useState, useEffect, useCallback } from 'react'
import { BarChart2, RefreshCw, Loader2, ChevronDown, ChevronRight } from 'lucide-react'
import { getCurrentDeal } from '../api/pipelineRuns'
import { getPipelineTimeline } from '../api/financials'
import type { PipelineTimelineRun } from '../api/financials'

const STATUS_COLOR: Record<string, string> = {
  complete: '#24a148',
  running:  '#0f62fe',
  partial:  '#f1c21b',
  error:    '#da1e28',
  skipped:  '#a8a8a8',
}

function formatElapsed(ms: number): string {
  if (!ms) return '—'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`
}

function formatTs(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

interface GanttBarProps {
  run: PipelineTimelineRun
}

function GanttBars({ run }: GanttBarProps) {
  if (!run.stages?.length) return <p className="text-[10px] text-[#a8a8a8] italic px-3 py-2">No stage data.</p>

  const totalMs = run.total_elapsed_ms || run.stages.reduce((s, st) => s + (st.elapsed_ms || 0), 0) || 1
  const barHeight = 18
  const labelWidth = 80
  const chartWidth = 320
  const rowGap = 4

  // Compute cumulative start offsets (sequential approximation)
  const stagesWithOffset = run.stages.map((s) => ({ ...s, elapsed_ms: s.elapsed_ms || 0 }))

  return (
    <div className="px-3 pb-3 pt-1 bg-[#fafafa] overflow-x-auto">
      <svg
        width={labelWidth + chartWidth + 60}
        height={stagesWithOffset.length * (barHeight + rowGap) + 24}
      >
        {/* X-axis label */}
        <text x={labelWidth} y={12} fontSize={8} fill="#8d8d8d">0</text>
        <text x={labelWidth + chartWidth} y={12} fontSize={8} fill="#8d8d8d" textAnchor="end">
          {formatElapsed(totalMs)}
        </text>

        {stagesWithOffset.map((s, i) => {
          const barW = Math.max((s.elapsed_ms / totalMs) * chartWidth, 4)
          // Compute simple sequential x offset
          const prevMs = stagesWithOffset.slice(0, i).reduce((acc, st) => acc + st.elapsed_ms, 0)
          const xOff = (prevMs / totalMs) * chartWidth
          const y = 18 + i * (barHeight + rowGap)
          const color = STATUS_COLOR[s.status] ?? '#525252'

          return (
            <g key={s.agent_name + i}>
              {/* Label */}
              <text x={labelWidth - 4} y={y + barHeight / 2 + 4} fontSize={9} fill="#525252" textAnchor="end">
                {s.agent_name}
              </text>
              {/* Bar background */}
              <rect x={labelWidth} y={y} width={chartWidth} height={barHeight} fill="#f0f0f0" rx={2} />
              {/* Bar fill */}
              <rect
                x={labelWidth + xOff}
                y={y}
                width={barW}
                height={barHeight}
                fill={color}
                rx={2}
                opacity={0.85}
              />
              {/* Elapsed label */}
              <text
                x={labelWidth + xOff + barW + 4}
                y={y + barHeight / 2 + 4}
                fontSize={8}
                fill="#525252"
              >
                {formatElapsed(s.elapsed_ms)}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

export default function PipelineGantt() {
  const [runs, setRuns] = useState<PipelineTimelineRun[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [expandedRun, setExpandedRun] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const deal = await getCurrentDeal()
      const result = await getPipelineTimeline(deal.deal_id ?? undefined, 5)
      setRuns(result)
    } catch {
      setError('Failed to load pipeline timeline')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (expanded && runs.length === 0) load()
  }, [expanded, runs.length, load])

  return (
    <div className="mt-4 border border-[#e0e0e0] rounded bg-white overflow-hidden">
      <div
        role="button"
        tabIndex={0}
        className="w-full flex items-center justify-between px-4 py-3 text-xs font-semibold text-[#161616] hover:bg-[#f4f4f4] transition-colors cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setExpanded((v) => !v) }}
      >
        <span className="flex items-center gap-2">
          <BarChart2 size={13} className="text-[#0f62fe]" />
          Pipeline Run Timeline
          {runs.length > 0 && (
            <span className="ml-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-[#e8e8e8] text-[#525252]">
              {runs.length} run{runs.length !== 1 ? 's' : ''}
            </span>
          )}
        </span>
        <div className="flex items-center gap-2">
          {expanded && (
            <button
              onClick={(e) => { e.stopPropagation(); load() }}
              disabled={loading}
              className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded disabled:opacity-50"
            >
              <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
            </button>
          )}
          <span className="text-[#8d8d8d]">{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-[#e0e0e0]">
          {loading && (
            <div className="flex items-center gap-2 px-4 py-3">
              <Loader2 size={14} className="animate-spin text-[#0f62fe]" />
              <span className="text-xs text-[#6f6f6f]">Loading…</span>
            </div>
          )}
          {error && !loading && (
            <p className="text-xs text-[#a8a8a8] italic px-4 py-3">{error}</p>
          )}
          {!loading && runs.length === 0 && (
            <p className="text-xs text-[#a8a8a8] italic px-4 py-3">
              No pipeline runs yet.
            </p>
          )}
          {!loading && runs.map((run) => {
            const isOpen = expandedRun === run.pipeline_run_id
            const color = STATUS_COLOR[run.status] ?? '#525252'
            const bg = run.status === 'complete' ? '#defbe6'
              : run.status === 'running' ? '#edf4ff'
              : run.status === 'partial' ? '#fdf6dd' : '#fff1f1'
            return (
              <div key={run.pipeline_run_id} className="border-b border-[#f4f4f4] last:border-0">
                <button
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-[#f4f4f4] transition-colors"
                  onClick={() => setExpandedRun(isOpen ? null : run.pipeline_run_id)}
                >
                  {isOpen ? <ChevronDown size={11} className="shrink-0 text-[#8d8d8d]" /> : <ChevronRight size={11} className="shrink-0 text-[#8d8d8d]" />}
                  <span
                    className="text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0"
                    style={{ color, backgroundColor: bg }}
                  >
                    {run.status}
                  </span>
                  <span className="text-[11px] text-[#161616] font-mono truncate flex-1">
                    {run.pipeline_run_id.slice(0, 12)}…
                  </span>
                  <span className="text-[10px] text-[#8d8d8d] shrink-0">{formatTs(run.started_at)}</span>
                  <span className="text-[10px] text-[#8d8d8d] shrink-0 ml-2">
                    {formatElapsed(run.total_elapsed_ms ?? 0)}
                  </span>
                </button>

                {isOpen && <GanttBars run={run} />}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
