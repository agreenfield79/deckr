import { useState, useEffect, useCallback } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Download,
  RefreshCw,
  Edit3,
  Loader2,
  Zap,
  Check,
  X,
} from 'lucide-react'
import * as deckApi from '../api/deck'
import MarkdownViewer from '../editor/MarkdownViewer'
import { useToast } from '../context/ToastContext'
import { useProject } from '../context/ProjectContext'
import { useSession } from '../hooks/useSession'

const SECTION_NAMES = [
  'Credit Request Summary',
  'Business Overview',
  'Financial Analysis',
  'Leverage',
  'Liquidity',
  'Collateral',
  'Guarantor',
  'Industry',
  'Risks',
  'Mitigants',
  'SLACR Score',
  'Recommendation',
  'Structure',
] as const

type SectionName = (typeof SECTION_NAMES)[number]

function parseSections(markdown: string): Record<string, string> {
  const sections: Record<string, string> = {}
  // Match ## N. Section Name\n\n{content} up to the next ---\n or ## N. or end
  const regex = /## \d+\. (.+?)\n\n([\s\S]*?)(?=\n\n---|\n## \d+\.|$)/g
  let match
  while ((match = regex.exec(markdown)) !== null) {
    const name = match[1].trim()
    const content = match[2].trim()
    if (SECTION_NAMES.includes(name as SectionName)) {
      sections[name] = content
    }
  }
  return sections
}

function reconstructDeck(
  original: string,
  sectionName: string,
  newContent: string,
): string {
  const idx = (SECTION_NAMES as readonly string[]).indexOf(sectionName) + 1
  if (idx === 0) return original
  const headingEscaped = `## ${idx}. ${sectionName}`.replace(
    /[.*+?^${}()|[\]\\]/g,
    '\\$&',
  )
  const pattern = new RegExp(
    `(${headingEscaped}\\n\\n)([\\s\\S]*?)(?=\\n\\n---|\\n## \\d+\\.|$)`,
  )
  return original.replace(pattern, `$1${newContent.trim()}`)
}

export default function DeckTab() {
  const { refreshTree } = useProject()
  const { sessionId } = useSession()
  const { success: toastSuccess, error: toastError } = useToast()

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

  const fetchDeck = useCallback(async () => {
    setLoading(true)
    try {
      const res = await deckApi.getDeck()
      if (res.exists && res.content) {
        setDeckContent(res.content)
        setSections(parseSections(res.content))
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
          ? 'Full deck generated → Deck/deck.md'
          : `Deck assembled from ${res.sections_loaded} existing sections → Deck/deck.md`
      toastSuccess(msg)
    } catch {
      toastError('Deck generation failed')
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
    a.download = 'deck.md'
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
            Your deck hasn't been generated yet
          </h2>
          <p className="text-xs text-[#6f6f6f] mb-5 leading-relaxed">
            Complete the onboarding form, upload supporting documents, and run
            the agents. Then generate your full 13-section Credit Memorandum.
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
            {generating ? 'Generating…' : 'Generate Deck'}
          </button>
        </div>
      </div>
    )
  }

  // ── Deck view ──────────────────────────────────────────────────────────────
  const completedCount = SECTION_NAMES.filter(
    (n) => sections[n] && !sections[n].startsWith('> **PENDING**'),
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
            {completedCount}/{SECTION_NAMES.length} sections
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
        </div>
      </div>

      {/* Section cards */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {SECTION_NAMES.map((name, idx) => {
          const isExpanded = expanded.has(name)
          const isEditing = editingSection === name
          const isRegenerating = regeneratingSection === name
          const content = sections[name] ?? ''
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
                      <p className="text-xs text-[#8d6708] italic">
                        Not yet generated. Click &ldquo;Regenerate Section&rdquo; to produce this content, or run the relevant agent from the Agent Panel.
                      </p>
                    ) : (
                      <MarkdownViewer content={content} />
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
