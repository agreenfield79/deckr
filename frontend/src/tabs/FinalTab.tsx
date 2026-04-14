import { useState, useEffect, useCallback, useRef } from 'react'
import { Download, FileText, Loader2 } from 'lucide-react'
import * as deckApi from '../api/deck'
import * as slacrApi from '../api/slacr'
import { getExtractedFinancials } from '../api/financials'
import type { ExtractedFinancials } from '../api/financials'
import type { SlacrOutput } from '../types/slacr'
import MarkdownViewer from '../editor/MarkdownViewer'
import { RevenueEbitdaChart, LeverageChart, SlacrRadarChart } from '../charts/FinancialCharts'
import { useToast } from '../context/ToastContext'

// Must match DeckTab.tsx SECTION_NAMES exactly
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

export default function FinalTab() {
  const { error: toastError } = useToast()
  const finalRef = useRef<HTMLDivElement>(null)

  const [sections, setSections] = useState<Record<string, string>>({})
  const [slacrData, setSlacrData] = useState<SlacrOutput | null>(null)
  const [financials, setFinancials] = useState<ExtractedFinancials | null>(null)
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

  const completedCount = SECTION_NAMES.filter(
    (n) => sections[n] && !sections[n].startsWith('> **PENDING**'),
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
            {completedCount}/{SECTION_NAMES.length} sections
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
          {SECTION_NAMES.map((name, idx) => {
            const content = sections[name] ?? ''
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
                {name === 'Financial Analysis' && (
                  <RevenueEbitdaChart data={financials} />
                )}
                {name === 'Leverage' && (
                  <LeverageChart data={financials} />
                )}
                {name === 'SLACR Score' && slacrData && (
                  <SlacrRadarChart data={slacrData} />
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
