import { useState, useEffect, useCallback, useRef } from 'react'
import { Download, FileText, Loader2, Zap } from 'lucide-react'
import * as deckrApi from '../api/deckr'
import MarkdownViewer from '../editor/MarkdownViewer'
import { useToast } from '../context/ToastContext'

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

export default function DeckrTab() {
  const { error: toastError } = useToast()
  const deckrRef = useRef<HTMLDivElement>(null)

  const [sections, setSections] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [hasContent, setHasContent] = useState(false)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const res = await deckrApi.getDeckr()
      if (res.exists && res.content) {
        setSections(parseSections(res.content))
        setHasContent(true)
      } else {
        setSections({})
        setHasContent(false)
      }
    } catch {
      toastError('Failed to load deal sheet')
    } finally {
      setLoading(false)
    }
  }, [toastError])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  const handleDownloadPdf = () => {
    const el = deckrRef.current
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

  const sectionEntries = Object.entries(sections)
  const completedCount = sectionEntries.filter(
    ([, content]) => content && !content.startsWith('> **PENDING**'),
  ).length

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={20} className="animate-spin text-[#ff832b]" />
      </div>
    )
  }

  if (!hasContent) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 px-8">
        <div className="max-w-sm text-center">
          <Zap size={36} className="mx-auto mb-3 text-[#ff832b] opacity-60" />
          <h2 className="text-sm font-semibold text-[#161616] mb-1">
            Deal Sheet not yet generated
          </h2>
          <p className="text-xs text-[#6f6f6f] leading-relaxed">
            Generate the Credit Memorandum first, then run the Deckr Agent from the
            Proposal tab or Agent Panel to produce the borrower-facing deal sheet.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Toolbar — hidden when printing */}
      <div className="no-print flex items-center justify-between px-4 py-2 border-b border-[#e0e0e0] bg-[#f4f4f4] shrink-0">
        <div className="flex items-center gap-2">
          <FileText size={13} className="text-[#ff832b]" />
          <span className="text-xs font-semibold text-[#525252] uppercase tracking-wider">
            Deal Sheet
          </span>
          <span className="text-[10px] text-[#6f6f6f] bg-[#e0e0e0] px-1.5 py-0.5 rounded font-mono">
            {completedCount}/{sectionEntries.length} sections
          </span>
        </div>
        <button
          onClick={handleDownloadPdf}
          title="Print or save as PDF"
          className="flex items-center gap-1 px-2 py-1 text-xs text-white bg-[#ff832b] hover:bg-[#eb6200] rounded transition-colors"
        >
          <Download size={11} />
          Save as PDF
        </button>
      </div>

      {/* Document scroll area */}
      <div className="flex-1 overflow-y-auto bg-[#f4f4f4] py-6 px-4">
        {/* Letter-width document container — borrower-facing poster style */}
        <div
          id="deckr-deal-sheet"
          ref={deckrRef}
          className="mx-auto bg-white border border-[#e0e0e0]"
          style={{ maxWidth: '768px', padding: '48px 64px', minHeight: '1056px' }}
        >
          {/* Document header — borrower-facing accent color */}
          <div className="pb-4 mb-8" style={{ borderBottom: '3px solid #ff832b' }}>
            <div className="flex items-center gap-2 mb-2">
              <div
                className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest rounded"
                style={{ backgroundColor: '#fff2e8', color: '#eb6200' }}
              >
                Borrower Package
              </div>
              <div
                className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest rounded"
                style={{ backgroundColor: '#fff2e8', color: '#eb6200' }}
              >
                Confidential
              </div>
            </div>
            <h1 className="text-2xl font-bold text-[#161616] tracking-tight">
              Deal Sheet
            </h1>
            <p className="text-xs text-[#525252] mt-1">
              Prepared {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
              {' · '}Powered by Deckr
            </p>
          </div>

          {/* Sections */}
          {sectionEntries.map(([name, content], idx) => {
            const isPending = !content || content.startsWith('> **PENDING**')

            return (
              <div key={name} className="mb-8">
                {/* Section header with orange left border accent */}
                <div
                  className="flex items-baseline gap-3 mb-3 pb-1"
                  style={{ borderBottom: '1px solid #ffd9b5' }}
                >
                  <span
                    className="text-[10px] font-bold w-5 text-right shrink-0"
                    style={{ color: '#ff832b' }}
                  >
                    {idx + 1}
                  </span>
                  <h2 className="text-base font-bold text-[#161616]">{name}</h2>
                </div>

                {isPending ? (
                  <p className="text-xs text-[#a8a8a8] italic ml-8">
                    [Section pending — run Deckr Agent to generate]
                  </p>
                ) : (
                  <div className="text-sm ml-8">
                    <MarkdownViewer content={content} />
                  </div>
                )}
              </div>
            )
          })}

          {/* Footer */}
          <div className="mt-8 pt-4" style={{ borderTop: '1px solid #ffd9b5' }}>
            <p className="text-[10px] text-[#a8a8a8] text-center">
              Generated by Deckr · Powered by IBM watsonx · This document is prepared for the borrower's use in approaching prospective lenders.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
