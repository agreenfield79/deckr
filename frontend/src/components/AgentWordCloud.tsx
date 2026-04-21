/**
 * AgentWordCloud — displays TF-weighted word cloud from external evidence corpus.
 * Sources from GET /api/mongo/word-cloud?deal_id=
 * Collections: news_articles, reviews, court_filings, document_chunks, industry_reports.
 *
 * NOTE: react-wordcloud is intentionally NOT used here. Its internal D3 spiral layout
 * reads index [0] from an undefined array when the container has zero width at mount
 * time (hidden tab, pending flexbox layout, React StrictMode double-invoke). This is
 * an unrecoverable crash that happens inside a useEffect — React Error Boundaries cannot
 * catch useEffect errors, so there is no safe way to use the library in a tabbed layout.
 * The weighted-span renderer below is crash-safe and produces equivalent visual output.
 */

import { useState, useEffect, useCallback } from 'react'
import { Cloud, RefreshCw, Loader2 } from 'lucide-react'
import { getCurrentDeal } from '../api/pipelineRuns'
import { getWordCloud } from '../api/financials'
import type { WordCloudTerm } from '../api/financials'

interface WordCloudProps {
  terms: WordCloudTerm[]
}

// Weighted-span word cloud — size and opacity scale with term weight.
// No external library dependency; safe to render in hidden/zero-width containers.
function WordCloudRenderer({ terms }: WordCloudProps) {
  return (
    <div className="flex flex-wrap gap-1.5 p-3">
      {terms.slice(0, 60).map((t) => {
        const size = 10 + Math.round(t.weight * 14)
        const opacity = 0.5 + t.weight * 0.5
        return (
          <span
            key={t.text}
            className="inline-block text-[#0f62fe] font-medium cursor-default hover:opacity-100 transition-opacity"
            style={{ fontSize: `${size}px`, opacity }}
            title={`${t.text}: ${t.value} occurrences`}
          >
            {t.text}
          </span>
        )
      })}
    </div>
  )
}

export default function AgentWordCloud() {
  const [terms, setTerms] = useState<WordCloudTerm[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const deal = await getCurrentDeal()
      if (!deal.deal_id) { setTerms([]); return }
      const result = await getWordCloud(deal.deal_id)
      setTerms(result)
    } catch {
      setError('Failed to load word cloud')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="border border-[#e0e0e0] rounded bg-white overflow-hidden mb-3">
      <div className="flex items-center justify-between px-3 py-2 bg-[#f4f4f4] border-b border-[#e0e0e0]">
        <div className="flex items-center gap-2">
          <Cloud size={13} className="text-[#6929c4]" />
          <span className="text-xs font-semibold text-[#161616]">External Evidence Word Cloud</span>
          {terms.length > 0 && (
            <span className="text-[10px] text-[#8d8d8d]">{terms.length} terms</span>
          )}
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded transition-colors disabled:opacity-50"
        >
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 size={18} className="animate-spin text-[#6929c4]" />
        </div>
      )}
      {error && !loading && (
        <p className="text-xs text-[#a8a8a8] italic px-3 py-4">{error}</p>
      )}
      {!loading && !error && terms.length === 0 && (
        <p className="text-xs text-[#a8a8a8] italic px-3 py-4">
          No external evidence data yet — run enrichment first.
        </p>
      )}
      {!loading && !error && terms.length > 0 && (
        <WordCloudRenderer terms={terms} />
      )}
    </div>
  )
}
