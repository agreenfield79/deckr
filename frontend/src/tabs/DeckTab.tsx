import { useState, useEffect, useCallback, useRef } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Download,
  Printer,
  RefreshCw,
  Edit3,
  Loader2,
  Zap,
  Check,
  X,
  BarChart2,
} from 'lucide-react'
import * as deckApi from '../api/deck'
import * as slacrApi from '../api/slacr'
import { getExtractedFinancials } from '../api/financials'
import type { ExtractedFinancials } from '../api/financials'
import MarkdownViewer from '../editor/MarkdownViewer'
import { useToast } from '../context/ToastContext'
import { useProject } from '../context/ProjectContext'
import { useSession } from '../hooks/useSession'
import { getRatingColor } from '../types/slacr'
import type { SlacrOutput } from '../types/slacr'
import { RevenueEbitdaChart, LeverageChart, SlacrRadarChart } from '../charts/FinancialCharts'

function parseSections(markdown: string): Record<string, string> {
  const sections: Record<string, string> = {}
  // Accept any ## N. Section Name heading — not filtered to a static list.
  // This ensures content from the Orchestrate packaging agent (which produces
  // its own section schema) renders correctly without changing the agent prompt.
  const regex = /## \d+\. (.+?)\n\n([\s\S]*?)(?=\n\n---|\n## \d+\.|$)/g
  let match
  while ((match = regex.exec(markdown)) !== null) {
    const name = match[1].trim()
    const content = match[2].trim()
    sections[name] = content
  }
  return sections
}

function reconstructDeck(
  original: string,
  sectionName: string,
  newContent: string,
): string {
  const headingEscaped = sectionName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const pattern = new RegExp(
    `(## \\d+\\. ${headingEscaped}\\n\\n)([\\s\\S]*?)(?=\\n\\n---|\\n## \\d+\\.|$)`,
  )
  return original.replace(pattern, `$1${newContent.trim()}`)
}

export default function DeckTab() {
  const { refreshTree } = useProject()
  const { sessionId } = useSession()
  const { success: toastSuccess, error: toastError } = useToast()

  const deckPrintRef = useRef<HTMLDivElement>(null)

  const [deckContent, setDeckContent] = useState<string | null>(null)
  const [sections, setSections] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(
    new Set(['Credit Request Summary']),
  )
  const [editingSection, setEditingSection] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [regeneratingSection, setRegeneratingSection] = useState<string | null>(null)
  const [slacrData, setSlacrData] = useState<SlacrOutput | null>(null)
  const [financials, setFinancials] = useState<ExtractedFinancials | null>(null)

  const fetchDeck = useCallback(async () => {
    setLoading(true)
    try {
      const [deckRes] = await Promise.all([
        deckApi.getDeck(),
        slacrApi.getScore().then(setSlacrData).catch(() => {}),
        getExtractedFinancials().then(setFinancials).catch(() => {}),
      ])
      if (deckRes.exists && deckRes.content) {
        setDeckContent(deckRes.content)
        setSections(parseSections(deckRes.content))
      } else {
        setDeckContent(null)
        setSections({})
      }
    } catch {
      toastError('Failed to load deck')
    } finally {
      setLoading(false)
    }
  }, [toastError])

  useEffect(() => {
    fetchDeck()
  }, [fetchDeck])

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const res = await deckApi.generateDeck(sessionId)
      await fetchDeck()
      await refreshTree()
      const msg =
        res.source === 'full_package'
          ? 'Full memo generated → Deck/memo.md'
          : `Memo assembled from ${res.sections_loaded} existing sections → Deck/memo.md`
      toastSuccess(msg)
    } catch {
      toastError('Memo generation failed')
    } finally {
      setGenerating(false)
    }
  }

  const handleRegenerateSection = async (sectionName: string) => {
    setRegeneratingSection(sectionName)
    try {
      const res = await deckApi.regenerateSection(sectionName, sessionId)
      setSections((prev) => ({ ...prev, [sectionName]: res.content }))
      // Update the in-memory deck content so Export stays in sync
      if (deckContent) {
        setDeckContent(reconstructDeck(deckContent, sectionName, res.content))
      }
      toastSuccess(`${sectionName} regenerated`)
    } catch {
      toastError(`Failed to regenerate ${sectionName}`)
    } finally {
      setRegeneratingSection(null)
    }
  }

  const handleSaveSection = async (sectionName: string) => {
    if (!deckContent) return
    const updated = reconstructDeck(deckContent, sectionName, editDraft)
    try {
      await deckApi.saveDeck(updated)
      setDeckContent(updated)
      setSections((prev) => ({ ...prev, [sectionName]: editDraft.trim() }))
      setEditingSection(null)
      toastSuccess(`${sectionName} saved`)
    } catch {
      toastError(`Failed to save ${sectionName}`)
    }
  }

  const handleExport = () => {
    if (!deckContent) return
    const blob = new Blob([deckContent], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'memo.md'
    a.click()
    URL.revokeObjectURL(url)
  }

  const toggleSection = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const handlePrint = () => {
    const el = deckPrintRef.current
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
    }
    window.addEventListener('afterprint', cleanup)

    window.print()
  }

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={20} className="animate-spin text-[#0f62fe]" />
      </div>
    )
  }

  // ── Empty / CTA state ──────────────────────────────────────────────────────
  if (!deckContent) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 px-8">
        <div className="max-w-sm text-center">
          <Zap size={36} className="mx-auto mb-3 text-[#0f62fe] opacity-60" />
          <h2 className="text-sm font-semibold text-[#161616] mb-1">
            Credit Memorandum not yet generated
          </h2>
          <p className="text-xs text-[#6f6f6f] mb-5 leading-relaxed">
            Complete the onboarding form, upload supporting documents, and run
            the agents. Then generate the full Credit Memorandum (memo.md).
          </p>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 mx-auto px-4 py-2 bg-[#0f62fe] text-white text-xs font-semibold rounded hover:bg-[#0043ce] disabled:opacity-50 transition-colors"
          >
            {generating ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Zap size={13} />
            )}
            {generating ? 'Generating…' : 'Generate Memo'}
          </button>
        </div>
      </div>
    )
  }

  // ── Deck view ──────────────────────────────────────────────────────────────
  const sectionEntries = Object.entries(sections)
  const completedCount = sectionEntries.filter(
    ([, content]) => content && !content.startsWith('> **PENDING**'),
  ).length

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#e0e0e0] bg-[#f4f4f4] shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-[#525252] uppercase tracking-wider">
            Credit Memorandum
          </span>
          <span className="text-[10px] text-[#6f6f6f] bg-[#e0e0e0] px-1.5 py-0.5 rounded font-mono">
            {completedCount}/{sectionEntries.length} sections
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleGenerate}
            disabled={generating || !!regeneratingSection}
            title="Regenerate full deck"
            className="flex items-center gap-1 px-2 py-1 text-xs text-[#0f62fe] border border-[#c6c6c6] bg-white hover:bg-[#edf4ff] rounded transition-colors disabled:opacity-50"
          >
            {generating ? (
              <Loader2 size={11} className="animate-spin" />
            ) : (
              <RefreshCw size={11} />
            )}
            Regenerate All
          </button>
          <button
            onClick={handleExport}
            title="Download as Markdown"
            className="flex items-center gap-1 px-2 py-1 text-xs text-[#525252] border border-[#c6c6c6] bg-white hover:bg-[#e0e0e0] rounded transition-colors"
          >
            <Download size={11} />
            Export
          </button>
          <button
            onClick={handlePrint}
            title="Print or save as PDF"
            className="flex items-center gap-1 px-2 py-1 text-xs text-white bg-[#0f62fe] hover:bg-[#0043ce] rounded transition-colors"
          >
            <Printer size={11} />
            Save as PDF
          </button>
        </div>
      </div>

      {/* Hidden flat-render print portal — off-screen, always rendered when deck is loaded */}
      <div
        ref={deckPrintRef}
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
        <div style={{ borderBottom: '2px solid #0f62fe', paddingBottom: '16px', marginBottom: '32px' }}>
          <p style={{ fontSize: '10px', color: '#6f6f6f', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600, marginBottom: '4px' }}>
            Confidential
          </p>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#161616' }}>Credit Memorandum</h1>
          <p style={{ fontSize: '12px', color: '#525252', marginTop: '4px' }}>
            Generated {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
          </p>
        </div>

        {sectionEntries.map(([name, content], idx) => {
          const isPending = !content || content.startsWith('> **PENDING**')
          return (
            <div key={name} style={{ marginBottom: '32px' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#161616', borderBottom: '1px solid #e0e0e0', paddingBottom: '4px', marginBottom: '12px' }}>
                {idx + 1}. {name}
              </h2>
              {isPending ? (
                <p style={{ fontSize: '12px', color: '#a8a8a8', fontStyle: 'italic' }}>
                  [Section pending — run agents to generate]
                </p>
              ) : (
                <div style={{ fontSize: '14px' }}>
                  <MarkdownViewer content={content} />
                </div>
              )}
              {name.includes('Financial Analysis') && <RevenueEbitdaChart data={financials} />}
              {(name === 'Leverage' || name.includes('Leverage & Capitalization')) && <LeverageChart data={financials} />}
              {(name === 'SLACR Score' || name.includes('SLACR Risk Rating')) && slacrData && (
                <>
                  <SlacrRadarChart data={slacrData} />
                  <SlacrScorePanel data={slacrData} />
                </>
              )}
            </div>
          )
        })}

        <div style={{ borderTop: '1px solid #e0e0e0', marginTop: '32px', paddingTop: '16px' }}>
          <p style={{ fontSize: '10px', color: '#a8a8a8', textAlign: 'center' }}>
            Generated by Deckr · Powered by IBM watsonx · Confidential and Proprietary
          </p>
        </div>
      </div>

      {/* Section cards */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {sectionEntries.map(([name, content], idx) => {
          const isExpanded = expanded.has(name)
          const isEditing = editingSection === name
          const isRegenerating = regeneratingSection === name
          const isPending =
            !content || content.startsWith('> **PENDING**')

          return (
            <div
              key={name}
              className={`border rounded overflow-hidden transition-colors ${
                isPending
                  ? 'border-[#f1c21b]'
                  : 'border-[#e0e0e0]'
              }`}
            >
              {/* Card header — click to expand/collapse */}
              <button
                className={`w-full flex items-center gap-2 px-3 py-2.5 text-left transition-colors ${
                  isPending ? 'bg-[#fdf6dd] hover:bg-[#faeeca]' : 'bg-white hover:bg-[#f4f4f4]'
                }`}
                onClick={() => toggleSection(name)}
              >
                {isExpanded ? (
                  <ChevronDown size={13} className="shrink-0 text-[#6f6f6f]" />
                ) : (
                  <ChevronRight size={13} className="shrink-0 text-[#6f6f6f]" />
                )}
                <span className="text-[10px] text-[#a8a8a8] font-mono w-5 shrink-0 text-right">
                  {idx + 1}
                </span>
                <span
                  className={`text-xs font-semibold flex-1 ${
                    isPending ? 'text-[#8d6708]' : 'text-[#161616]'
                  }`}
                >
                  {name}
                </span>
                {isPending ? (
                  <span className="text-[10px] text-[#8d6708] bg-[#f1c21b]/40 px-1.5 py-0.5 rounded shrink-0">
                    Pending
                  </span>
                ) : (
                  <span className="text-[#24a148] shrink-0">
                    <Check size={12} />
                  </span>
                )}
              </button>

              {/* Card body */}
              {isExpanded && (
                <div className="border-t border-[#e0e0e0]">
                  {/* Action bar */}
                  <div className="flex items-center gap-3 px-3 py-1.5 bg-[#f4f4f4] border-b border-[#e0e0e0]">
                    {!isEditing ? (
                      <button
                        onClick={() => {
                          setEditingSection(name)
                          setEditDraft(content)
                        }}
                        className="flex items-center gap-1 text-[10px] text-[#525252] hover:text-[#0f62fe] transition-colors"
                      >
                        <Edit3 size={10} />
                        Edit
                      </button>
                    ) : (
                      <>
                        <button
                          onClick={() => handleSaveSection(name)}
                          className="flex items-center gap-1 text-[10px] text-[#24a148] hover:text-[#198038] font-semibold transition-colors"
                        >
                          <Check size={10} />
                          Save
                        </button>
                        <button
                          onClick={() => setEditingSection(null)}
                          className="flex items-center gap-1 text-[10px] text-[#525252] hover:text-[#da1e28] transition-colors"
                        >
                          <X size={10} />
                          Cancel
                        </button>
                      </>
                    )}
                    {!isEditing && (
                      <>
                        <span className="text-[#e0e0e0]">|</span>
                        <button
                          onClick={() => handleRegenerateSection(name)}
                          disabled={!!regeneratingSection || generating}
                          className="flex items-center gap-1 text-[10px] text-[#525252] hover:text-[#0f62fe] disabled:opacity-50 transition-colors"
                        >
                          {isRegenerating ? (
                            <Loader2 size={10} className="animate-spin" />
                          ) : (
                            <RefreshCw size={10} />
                          )}
                          {isRegenerating ? 'Regenerating…' : 'Regenerate Section'}
                        </button>
                      </>
                    )}
                  </div>

                  {/* Content */}
                  <div className={`px-4 py-3 ${isPending && !isEditing ? 'bg-[#fdf6dd]' : 'bg-white'}`}>
                    {isEditing ? (
                      <textarea
                        value={editDraft}
                        onChange={(e) => setEditDraft(e.target.value)}
                        className="w-full text-xs font-mono text-[#161616] bg-[#f4f4f4] border border-[#c6c6c6] rounded p-2 resize-y min-h-40 focus:outline-none focus:ring-1 focus:ring-[#0f62fe]"
                        rows={12}
                        autoFocus
                      />
                    ) : isPending ? (
                      <>
                        <p className="text-xs text-[#8d6708] italic">
                          Not yet generated. Click &ldquo;Regenerate Section&rdquo; to produce this content, or run the relevant agent from the Agent Panel.
                        </p>
                        {(name === 'SLACR Score' || name.includes('SLACR Risk Rating')) && slacrData && (
                          <SlacrScorePanel data={slacrData} />
                        )}
                      </>
                    ) : (
                      <>
                        <MarkdownViewer content={content} />
                        {name.includes('Financial Analysis') && (
                          <RevenueEbitdaChart data={financials} />
                        )}
                        {(name === 'Leverage' || name.includes('Leverage & Capitalization')) && (
                          <LeverageChart data={financials} />
                        )}
                        {/* SLACR section: show radar + live data panel from slacr.json */}
                        {(name === 'SLACR Score' || name.includes('SLACR Risk Rating')) && slacrData && (
                          <>
                            <SlacrRadarChart data={slacrData} />
                            <SlacrScorePanel data={slacrData} />
                          </>
                        )}
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SLACR Score inline panel — shown inside the "SLACR Score" deck section
// ---------------------------------------------------------------------------

const DIMENSION_LABELS: Record<string, string> = {
  strength:         'Sponsor / Management',
  leverage:         'Leverage & Capitalization',
  ability_to_repay: 'Ability to Repay',
  collateral:       'Collateral Quality',
  risk_factors:     'Industry & Market Risk',
}

function SlacrScorePanel({ data }: { data: SlacrOutput }) {
  const ratingColor = getRatingColor(data.weighted_score)
  return (
    <div className="mt-4 border border-[#e0e0e0] rounded-lg overflow-hidden">
      <div
        className="px-4 py-2.5 flex items-center justify-between"
        style={{ backgroundColor: `${ratingColor}18` }}
      >
        <div className="flex items-center gap-2">
          <BarChart2 size={13} style={{ color: ratingColor }} />
          <span className="text-xs font-semibold text-[#161616]">SLACR Live Score</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-bold" style={{ color: ratingColor }}>
            {data.weighted_score.toFixed(2)}
          </span>
          <span className="text-xs font-medium" style={{ color: ratingColor }}>
            {data.rating}
          </span>
          <span className="text-xs text-[#525252]">→ {data.decision}</span>
        </div>
      </div>

      {/* Dimension scores table */}
      <table className="w-full text-xs border-t border-[#e0e0e0]">
        <thead>
          <tr className="bg-[#f4f4f4]">
            <th className="text-left px-3 py-1.5 text-[10px] font-semibold text-[#525252] uppercase tracking-wider">
              Dimension
            </th>
            <th className="text-center px-3 py-1.5 text-[10px] font-semibold text-[#525252] uppercase tracking-wider">
              Score
            </th>
            <th className="text-left px-3 py-1.5 text-[10px] font-semibold text-[#525252] uppercase tracking-wider">
              Notes
            </th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(DIMENSION_LABELS).map(([field, label]) => {
            const score = data.input[field as keyof typeof data.input] as number
            const noteText = data.input.notes[label] ?? ''
            return (
              <tr key={field} className="border-t border-[#f4f4f4]">
                <td className="px-3 py-1.5 text-[#161616]">{label}</td>
                <td className="px-3 py-1.5 text-center">
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-semibold"
                    style={{
                      color:           score <= 2 ? '#24a148' : score >= 4 ? '#da1e28' : '#8d6708',
                      backgroundColor: score <= 2 ? '#defbe6' : score >= 4 ? '#fff1f1' : '#fdf6dd',
                    }}
                  >
                    {score}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-[#525252] italic text-[10px]">
                  {noteText || '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {/* Mitigants */}
      {data.mitigants.length > 0 &&
        data.mitigants[0] !== 'Standard monitoring and covenant compliance' && (
          <div className="border-t border-[#e0e0e0] px-4 py-3">
            <p className="text-[10px] font-semibold text-[#525252] uppercase tracking-wider mb-1.5">
              Recommended Conditions
            </p>
            <ul className="space-y-1">
              {data.mitigants.map((m, i) => (
                <li key={i} className="flex gap-1.5 text-xs text-[#525252]">
                  <span className="text-[#0f62fe] shrink-0">·</span>
                  {m}
                </li>
              ))}
            </ul>
          </div>
        )}
    </div>
  )
}
