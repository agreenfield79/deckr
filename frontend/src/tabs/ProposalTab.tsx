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
} from 'lucide-react'
import * as deckrApi from '../api/deckr'
import MarkdownViewer from '../editor/MarkdownViewer'
import { useToast } from '../context/ToastContext'
import { useProject } from '../context/ProjectContext'
import { useSession } from '../hooks/useSession'

function parseSections(markdown: string): Record<string, string> {
  const sections: Record<string, string> = {}
  // Normalize line endings; accept one or more newlines between heading and content.
  const normalized = markdown.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const regex = /## \d+\. (.+?)\n+([\s\S]*?)(?=\n## \d+\.|$)/g
  let match
  while ((match = regex.exec(normalized)) !== null) {
    sections[match[1].trim()] = match[2].trim()
  }
  return sections
}

function reconstructDealSheet(
  original: string,
  sectionName: string,
  newContent: string,
): string {
  const normalized = original.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const headingEscaped = sectionName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  // [^\n]* after the section name tolerates trailing spaces/line-breaks that
  // the deckr agent sometimes appends to headings (e.g. "## 5. Loan Structure  ")
  const pattern = new RegExp(
    `(## \\d+\\. ${headingEscaped}[^\\n]*\\n+)([\\s\\S]*?)(?=\\n## \\d+\\.|$)`,
  )
  return normalized.replace(pattern, `$1${newContent.trim()}\n`)
}

export default function ProposalTab() {
  const { refreshTree } = useProject()
  const { sessionId } = useSession()
  const { success: toastSuccess, error: toastError } = useToast()

  const proposalPrintRef = useRef<HTMLDivElement>(null)

  const [deckrContent, setDeckrContent] = useState<string | null>(null)
  const [sections, setSections] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['Header']))
  const [editingSection, setEditingSection] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [regeneratingSection, setRegeneratingSection] = useState<string | null>(null)

  const fetchDeckr = useCallback(async () => {
    setLoading(true)
    try {
      const res = await deckrApi.getDeckr()
      if (res.exists && res.content) {
        setDeckrContent(res.content)
        setSections(parseSections(res.content))
      } else {
        setDeckrContent(null)
        setSections({})
      }
    } catch {
      toastError('Failed to load deal sheet')
    } finally {
      setLoading(false)
    }
  }, [toastError])

  useEffect(() => {
    fetchDeckr()
  }, [fetchDeckr])

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      await deckrApi.generateDeckr(sessionId)
      await fetchDeckr()
      await refreshTree()
      toastSuccess('Deal sheet generated → Deck/deckr.md')
    } catch {
      toastError('Deal sheet generation failed')
    } finally {
      setGenerating(false)
    }
  }

  const handleRegenerateSection = async (sectionName: string) => {
    setRegeneratingSection(sectionName)
    try {
      const res = await deckrApi.regenerateDeckrSection(sectionName, sessionId)
      setSections((prev) => ({ ...prev, [sectionName]: res.content }))
      if (deckrContent) {
        setDeckrContent(reconstructDealSheet(deckrContent, sectionName, res.content))
      }
      toastSuccess(`${sectionName} regenerated`)
    } catch {
      toastError(`Failed to regenerate ${sectionName}`)
    } finally {
      setRegeneratingSection(null)
    }
  }

  const handleSaveSection = async (sectionName: string) => {
    if (!deckrContent) return
    const updated = reconstructDealSheet(deckrContent, sectionName, editDraft)
    try {
      await deckrApi.saveDeckr(updated)
      setDeckrContent(updated)
      setSections((prev) => ({ ...prev, [sectionName]: editDraft.trim() }))
      setEditingSection(null)
      toastSuccess(`${sectionName} saved`)
    } catch {
      toastError(`Failed to save ${sectionName}`)
    }
  }

  const handleExport = () => {
    if (!deckrContent) return
    const blob = new Blob([deckrContent], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'deckr.md'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handlePrint = () => {
    const el = proposalPrintRef.current
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

  const toggleSection = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={20} className="animate-spin text-[#0f62fe]" />
      </div>
    )
  }

  if (!deckrContent) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 px-8">
        <div className="max-w-sm text-center">
          <Zap size={36} className="mx-auto mb-3 text-[#ff832b] opacity-60" />
          <h2 className="text-sm font-semibold text-[#161616] mb-1">
            Deal Sheet not yet generated
          </h2>
          <p className="text-xs text-[#6f6f6f] mb-5 leading-relaxed">
            Complete the analysis pipeline to generate the Credit Memorandum first, then
            generate the borrower-facing Deal Sheet (deckr.md).
          </p>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 mx-auto px-4 py-2 bg-[#ff832b] text-white text-xs font-semibold rounded hover:bg-[#eb6200] disabled:opacity-50 transition-colors"
          >
            {generating ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Zap size={13} />
            )}
            {generating ? 'Generating…' : 'Generate Deal Sheet'}
          </button>
        </div>
      </div>
    )
  }

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
            Deal Sheet
          </span>
          <span className="text-[10px] text-[#6f6f6f] bg-[#e0e0e0] px-1.5 py-0.5 rounded font-mono">
            {completedCount}/{sectionEntries.length} sections
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleGenerate}
            disabled={generating || !!regeneratingSection}
            title="Regenerate full deal sheet"
            className="flex items-center gap-1 px-2 py-1 text-xs text-[#ff832b] border border-[#c6c6c6] bg-white hover:bg-[#fff2e8] rounded transition-colors disabled:opacity-50"
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
            className="flex items-center gap-1 px-2 py-1 text-xs text-white bg-[#ff832b] hover:bg-[#eb6200] rounded transition-colors"
          >
            <Printer size={11} />
            Save as PDF
          </button>
        </div>
      </div>

      {/* Hidden flat-render print portal — off-screen, always rendered when deal sheet is loaded */}
      <div
        ref={proposalPrintRef}
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
        <div style={{ borderBottom: '2px solid #ff832b', paddingBottom: '16px', marginBottom: '32px' }}>
          <p style={{ fontSize: '10px', color: '#6f6f6f', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600, marginBottom: '4px' }}>
            Confidential — Borrower Package
          </p>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#161616' }}>Deal Sheet</h1>
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
                  [Section pending — regenerate to produce content]
                </p>
              ) : (
                <div style={{ fontSize: '14px' }}>
                  <MarkdownViewer content={content} />
                </div>
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
          const isPending = !content || content.startsWith('> **PENDING**')

          return (
            <div
              key={name}
              className={`border rounded overflow-hidden transition-colors ${
                isPending ? 'border-[#f1c21b]' : 'border-[#e0e0e0]'
              }`}
            >
              {/* Card header */}
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
                        className="flex items-center gap-1 text-[10px] text-[#525252] hover:text-[#ff832b] transition-colors"
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
                          className="flex items-center gap-1 text-[10px] text-[#525252] hover:text-[#ff832b] disabled:opacity-50 transition-colors"
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
                        className="w-full text-xs font-mono text-[#161616] bg-[#f4f4f4] border border-[#c6c6c6] rounded p-2 resize-y min-h-40 focus:outline-none focus:ring-1 focus:ring-[#ff832b]"
                        rows={12}
                        autoFocus
                      />
                    ) : isPending ? (
                      <p className="text-xs text-[#8d6708] italic">
                        Not yet generated. Click &ldquo;Regenerate Section&rdquo; or run the Deckr Agent from the Agent Panel.
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
