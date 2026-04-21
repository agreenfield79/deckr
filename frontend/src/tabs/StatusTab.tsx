import { useState, useRef, useEffect } from 'react'
import { CheckCircle, Clock, ArrowRight, RefreshCw, Printer, Server, Database, Cpu, History, ChevronDown, ChevronRight } from 'lucide-react'
import { useStatus } from '../hooks/useStatus'
import { getDeck } from '../api/deck'
import MarkdownViewer from '../editor/MarkdownViewer'
import type { TabId } from './TabBar'
import { useConfig } from '../context/ConfigContext'
import { getPipelineHistory, type PipelineRun } from '../api/pipelineRuns'
import PipelineGantt from '../components/PipelineGantt'

function parseSections(markdown: string): Record<string, string> {
  const sections: Record<string, string> = {}
  const regex = /## \d+\. (.+?)\n\n([\s\S]*?)(?=\n\n---|\n## \d+\.|$)/g
  let match
  while ((match = regex.exec(markdown)) !== null) {
    sections[match[1].trim()] = match[2].trim()
  }
  return sections
}

interface StatusTabProps {
  onNavigate: (tab: TabId) => void
}

function motivate(percentage: number): string {
  if (percentage === 100) return 'Your package is complete! Review the deck and submit for credit committee review.'
  if (percentage >= 75)   return `Your package is ${percentage}% complete — almost there!`
  if (percentage >= 50)   return `Your package is ${percentage}% complete. Here's what's left:`
  if (percentage >= 25)   return `Your package is ${percentage}% complete. Keep going!`
  return `Your package is ${percentage}% complete. Let's get started!`
}

export default function StatusTab({ onNavigate }: StatusTabProps) {
  const { items, percentage, loading, refresh } = useStatus()
  const { health, healthLoading, refreshHealth } = useConfig()

  const [printContent, setPrintContent] = useState<string>('')
  const [printing, setPrinting] = useState(false)
  const statusPrintRef = useRef<HTMLDivElement>(null)

  const handlePrintAll = async () => {
    setPrinting(true)
    try {
      const res = await getDeck()
      if (!res.exists || !res.content) {
        alert('No Credit Memorandum yet — run the agents to generate it first.')
        return
      }
      setPrintContent(res.content)
    } catch {
      alert('Failed to load Credit Memorandum for printing.')
    } finally {
      setPrinting(false)
    }
  }

  useEffect(() => {
    if (!printContent || !statusPrintRef.current) return

    requestAnimationFrame(() => {
      const el = statusPrintRef.current
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
            position: static !important;
            left: auto !important;
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

      const cleanup = () => {
        document.body.removeChild(clone)
        document.head.removeChild(style)
        window.removeEventListener('afterprint', cleanup)
        setPrintContent('')
      }
      window.addEventListener('afterprint', cleanup)

      window.print()
    })
  }, [printContent])

  const completeCount = items.filter((i) => i.complete).length

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5">
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h2 className="text-sm font-semibold text-[#161616]">Package Status</h2>
          <p className="text-xs text-[#6f6f6f] mt-1 max-w-sm leading-relaxed">
            {motivate(percentage)}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={handlePrintAll}
            disabled={printing}
            title="Print full deal package as PDF (bank track)"
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-white bg-[#0f62fe] hover:bg-[#0043ce] rounded transition-colors disabled:opacity-50"
          >
            <Printer size={11} className={printing ? 'animate-pulse' : ''} />
            {printing ? 'Loading…' : 'Print All'}
          </button>
          <button
            onClick={refresh}
            disabled={loading}
            title="Re-check status"
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-[#525252] border border-[#c6c6c6] bg-white hover:bg-[#e0e0e0] rounded transition-colors disabled:opacity-50"
          >
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] font-medium text-[#525252] uppercase tracking-wider">
            Overall Completeness
          </span>
          <span className="text-xs font-semibold text-[#161616]">{percentage}%</span>
        </div>
        <div className="h-2.5 bg-[#e0e0e0] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${percentage}%`,
              backgroundColor:
                percentage === 100 ? '#24a148' : percentage >= 75 ? '#0f62fe' : '#0f62fe',
            }}
          />
        </div>
        <div className="flex justify-between mt-1.5">
          <span className="text-[10px] text-[#6f6f6f]">
            {completeCount} of {items.length} items complete
          </span>
          {percentage === 100 && (
            <span className="text-[10px] text-[#24a148] font-semibold">
              ✓ Ready for review
            </span>
          )}
        </div>
      </div>

      {/* Hidden flat-render print portal for Print All — bank track (memo.md) */}
      <div
        ref={statusPrintRef}
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: '-9999px',
          top: 0,
          width: '768px',
          background: 'white',
          padding: '48px 64px',
        }}
      >
        {printContent && (
          <>
            <div style={{ borderBottom: '2px solid #0f62fe', paddingBottom: '16px', marginBottom: '32px' }}>
              <p style={{ fontSize: '10px', color: '#6f6f6f', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600, marginBottom: '4px' }}>
                Confidential
              </p>
              <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#161616' }}>Credit Memorandum</h1>
              <p style={{ fontSize: '12px', color: '#525252', marginTop: '4px' }}>
                Generated {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
              </p>
            </div>

            {Object.entries(parseSections(printContent)).map(([name, content], idx) => (
              <div key={name} style={{ marginBottom: '32px' }}>
                <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#161616', borderBottom: '1px solid #e0e0e0', paddingBottom: '4px', marginBottom: '12px' }}>
                  {idx + 1}. {name}
                </h2>
                {!content || content.startsWith('> **PENDING**') ? (
                  <p style={{ fontSize: '12px', color: '#a8a8a8', fontStyle: 'italic' }}>
                    [Section pending — run agents to generate]
                  </p>
                ) : (
                  <div style={{ fontSize: '14px' }}>
                    <MarkdownViewer content={content} />
                  </div>
                )}
              </div>
            ))}

            <div style={{ borderTop: '1px solid #e0e0e0', marginTop: '32px', paddingTop: '16px' }}>
              <p style={{ fontSize: '10px', color: '#a8a8a8', textAlign: 'center' }}>
                Generated by Deckr · Powered by IBM watsonx · Confidential and Proprietary
              </p>
            </div>
          </>
        )}
      </div>

      {/* Checklist */}
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.label}
            className={`flex items-center gap-3 px-3.5 py-2.5 rounded border transition-colors ${
              item.complete
                ? 'bg-[#defbe6] border-[#a7f0ba]'
                : 'bg-white border-[#e0e0e0] hover:border-[#c6c6c6]'
            }`}
          >
            {item.complete ? (
              <CheckCircle size={15} className="shrink-0 text-[#24a148]" />
            ) : (
              <Clock size={15} className="shrink-0 text-[#f1c21b]" />
            )}

            <span
              className={`text-xs flex-1 ${
                item.complete ? 'text-[#198038] font-medium' : 'text-[#161616]'
              }`}
            >
              {item.label}
            </span>

            {/* Navigation action for incomplete items */}
            {!item.complete && item.tab && item.action && (
              <button
                onClick={() => onNavigate(item.tab as TabId)}
                className="flex items-center gap-1 text-[10px] text-[#0f62fe] hover:text-[#0043ce] hover:underline shrink-0 transition-colors"
              >
                {item.action}
                <ArrowRight size={10} />
              </button>
            )}
            {!item.complete && !item.tab && item.action && (
              <span className="text-[10px] text-[#a8a8a8] shrink-0 italic">
                {item.action}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* System Health */}
      <SystemHealthPanel health={health} loading={healthLoading} onRefresh={refreshHealth} />

      {/* Pipeline Run History */}
      <PipelineHistoryPanel />

      {/* Pipeline Run Timeline — Gantt */}
      <PipelineGantt />
    </div>
  )
}

// ---------------------------------------------------------------------------
// SystemHealthPanel — shows /api/health response
// ---------------------------------------------------------------------------

interface SystemHealthPanelProps {
  health: import('../api/health').HealthResponse | null
  loading: boolean
  onRefresh: () => void
}

function SystemHealthPanel({ health, loading, onRefresh }: SystemHealthPanelProps) {
  const [expanded, setExpanded] = useState(false)

  const storageMode = health?.storage_mode ?? 'unknown'
  const features = health?.features
  const databases = health?.databases ?? health?.storage

  return (
    <div className="mt-6 border border-[#e0e0e0] rounded bg-white overflow-hidden">
      <div
        role="button"
        tabIndex={0}
        className="w-full flex items-center justify-between px-4 py-3 text-xs font-semibold text-[#161616] hover:bg-[#f4f4f4] transition-colors cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setExpanded((v) => !v) }}
      >
        <span className="flex items-center gap-2">
          <Server size={13} className="text-[#525252]" />
          System Health
          {health && (
            <span className={`ml-1 text-[10px] font-medium px-1.5 py-0.5 rounded ${
              health.status === 'ok' ? 'bg-[#defbe6] text-[#198038]' : 'bg-[#fff1f1] text-[#da1e28]'
            }`}>
              {health.status === 'ok' ? 'OK' : 'Degraded'}
            </span>
          )}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => { e.stopPropagation(); onRefresh() }}
            disabled={loading}
            title="Refresh health"
            className="p-1 text-[#525252] hover:text-[#161616] hover:bg-[#e0e0e0] rounded transition-colors disabled:opacity-50"
          >
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          </button>
          <span className="text-[#8d8d8d]">{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 text-xs">
          {/* Storage mode */}
          <div className="flex items-center gap-2 pt-1">
            <Database size={12} className="text-[#525252] shrink-0" />
            <span className="text-[#6f6f6f]">Storage:</span>
            <span className="font-medium text-[#161616] capitalize">{storageMode}</span>
          </div>

          {/* Database status */}
          {databases && (
            <div>
              <p className="text-[10px] font-semibold text-[#525252] uppercase tracking-wider mb-1.5">
                Databases
              </p>
              <div className="space-y-1">
                {Object.entries(databases).map(([db, status]) => {
                  const connected = typeof status === 'object' && status !== null
                    ? (status as { connected?: boolean }).connected
                    : false
                  return (
                    <div key={db} className="flex items-center justify-between px-2.5 py-1.5 bg-[#f4f4f4] rounded">
                      <span className="font-mono text-[11px] text-[#161616]">{db}</span>
                      <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                        connected ? 'bg-[#defbe6] text-[#198038]' : 'bg-[#e8e8e8] text-[#6f6f6f]'
                      }`}>
                        {connected ? 'Connected' : 'Offline'}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Feature flags */}
          {features && (
            <div>
              <p className="text-[10px] font-semibold text-[#525252] uppercase tracking-wider mb-1.5">
                Features
              </p>
              <div className="space-y-1">
                {Object.entries(features).map(([feat, enabled]) => (
                  <div key={feat} className="flex items-center justify-between px-2.5 py-1.5 bg-[#f4f4f4] rounded">
                    <span className="flex items-center gap-1.5">
                      <Cpu size={10} className="text-[#8d8d8d]" />
                      <span className="text-[11px] text-[#161616]">
                        {feat.replace(/_/g, ' ')}
                      </span>
                    </span>
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                      enabled ? 'bg-[#defbe6] text-[#198038]' : 'bg-[#e8e8e8] text-[#6f6f6f]'
                    }`}>
                      {enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!health && !loading && (
            <p className="text-[#6f6f6f] italic">Backend unavailable — health data not loaded.</p>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PipelineHistoryPanel — shows MongoDB pipeline run history
// ---------------------------------------------------------------------------

function formatElapsed(ms: number | undefined): string {
  if (!ms) return '—'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`
}

function formatTs(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

function PipelineHistoryPanel() {
  const [expanded, setExpanded]         = useState(false)
  const [runs, setRuns]                 = useState<PipelineRun[]>([])
  const [loading, setLoading]           = useState(false)
  const [expandedRun, setExpandedRun]   = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const res = await getPipelineHistory(undefined, 10)
      setRuns(res.runs ?? [])
    } catch {
      setRuns([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (expanded && runs.length === 0) load()
  }, [expanded])

  const statusColor = (s: string) =>
    s === 'complete' ? '#24a148' : s === 'running' ? '#0f62fe' : s === 'partial' ? '#f1c21b' : '#da1e28'
  const statusBg = (s: string) =>
    s === 'complete' ? '#defbe6' : s === 'running' ? '#edf4ff' : s === 'partial' ? '#fdf6dd' : '#fff1f1'

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
          <History size={13} className="text-[#525252]" />
          Pipeline Run History
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
              title="Refresh history"
              className="p-1 text-[#525252] hover:text-[#161616] hover:bg-[#e0e0e0] rounded transition-colors disabled:opacity-50"
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
            <div className="px-4 py-3 text-xs text-[#6f6f6f] italic">Loading…</div>
          )}
          {!loading && runs.length === 0 && (
            <div className="px-4 py-3 text-xs text-[#6f6f6f] italic">
              No pipeline runs yet — run the agents to start your first run.
            </div>
          )}
          {!loading && runs.map((run) => {
            const isOpen = expandedRun === run.pipeline_run_id
            return (
              <div key={run.pipeline_run_id} className="border-b border-[#f4f4f4] last:border-b-0">
                <button
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-[#f4f4f4] transition-colors"
                  onClick={() => setExpandedRun(isOpen ? null : run.pipeline_run_id)}
                >
                  {isOpen ? <ChevronDown size={11} className="shrink-0 text-[#8d8d8d]" /> : <ChevronRight size={11} className="shrink-0 text-[#8d8d8d]" />}
                  <span
                    className="text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0"
                    style={{ color: statusColor(run.status), backgroundColor: statusBg(run.status) }}
                  >
                    {run.status}
                  </span>
                  <span className="text-[11px] text-[#161616] font-mono truncate flex-1">
                    {run.pipeline_run_id.slice(0, 12)}…
                  </span>
                  <span className="text-[10px] text-[#8d8d8d] shrink-0">{formatTs(run.started_at)}</span>
                  <span className="text-[10px] text-[#8d8d8d] shrink-0 ml-2">
                    {formatElapsed(run.total_elapsed_ms)}
                  </span>
                </button>
                {isOpen && (run.stages?.length ?? 0) > 0 && (
                  <div className="px-4 pb-2 bg-[#f9f9f9]">
                    <table className="w-full text-[10px]">
                      <thead>
                        <tr className="text-[#8d8d8d] uppercase tracking-wider">
                          <th className="text-left py-1 pr-2 font-semibold">#</th>
                          <th className="text-left py-1 pr-2 font-semibold">Agent</th>
                          <th className="text-left py-1 pr-2 font-semibold">Status</th>
                          <th className="text-right py-1 font-semibold">Time</th>
                        </tr>
                      </thead>
                      <tbody>
                        {run.stages.map((s) => (
                          <tr key={`${s.stage_order}-${s.agent_name}`} className="border-t border-[#f0f0f0]">
                            <td className="py-1 pr-2 text-[#a8a8a8]">{s.stage_order}</td>
                            <td className="py-1 pr-2 font-medium text-[#161616]">{s.agent_name}</td>
                            <td className="py-1 pr-2">
                              <span style={{ color: statusColor(s.status) }}>{s.status}</span>
                            </td>
                            <td className="py-1 text-right text-[#525252]">
                              {formatElapsed(s.elapsed_ms)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {isOpen && !(run.stages?.length ?? 0) && (
                  <p className="px-4 pb-2 text-[10px] text-[#a8a8a8] italic bg-[#f9f9f9]">
                    Stage details not available (run pre-dates stage logging)
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
