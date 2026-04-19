/**
 * DocumentCoverageHeatmap — agent × document read matrix.
 * Sources from GET /api/mongo/document-coverage?deal_id=
 * Pure SVG/React implementation — no D3 dependency required.
 */

import { useState, useEffect, useCallback } from 'react'
import { Grid, RefreshCw, Loader2 } from 'lucide-react'
import { getCurrentDeal } from '../api/pipelineRuns'
import { getDocumentCoverage } from '../api/financials'
import type { DocumentCoverageResponse } from '../api/financials'

export default function DocumentCoverageHeatmap() {
  const [data, setData] = useState<DocumentCoverageResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const deal = await getCurrentDeal()
      if (!deal.deal_id) { setData(null); return }
      const result = await getDocumentCoverage(deal.deal_id)
      setData(result)
    } catch {
      setError('Failed to load document coverage')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 border border-[#e0e0e0] rounded bg-white mt-4">
        <Loader2 size={18} className="animate-spin text-[#0f62fe]" />
      </div>
    )
  }

  if (error || !data || data.documents.length === 0) {
    return (
      <div className="border border-[#e0e0e0] rounded bg-white overflow-hidden mt-4">
        <div className="flex items-center justify-between px-3 py-2 bg-[#f4f4f4] border-b border-[#e0e0e0]">
          <div className="flex items-center gap-2">
            <Grid size={13} className="text-[#525252]" />
            <span className="text-xs font-semibold text-[#161616]">Document Coverage Heatmap</span>
          </div>
          <button onClick={load} className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded"><RefreshCw size={11} /></button>
        </div>
        <p className="text-xs text-[#a8a8a8] italic px-3 py-4">
          {error ?? 'No document index data — run the pipeline to populate.'}
        </p>
      </div>
    )
  }

  const { agents, documents } = data

  return (
    <div className="border border-[#e0e0e0] rounded bg-white overflow-hidden mt-4">
      <div className="flex items-center justify-between px-3 py-2 bg-[#f4f4f4] border-b border-[#e0e0e0]">
        <div className="flex items-center gap-2">
          <Grid size={13} className="text-[#0f62fe]" />
          <span className="text-xs font-semibold text-[#161616]">Document Coverage Heatmap</span>
          <span className="text-[10px] text-[#8d8d8d]">{documents.length} docs · {agents.length} agents</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-[9px] text-[#525252]">
            <span className="w-3 h-3 rounded inline-block" style={{ backgroundColor: '#24a148' }} /> Read
            <span className="w-3 h-3 rounded inline-block ml-1" style={{ backgroundColor: '#e0e0e0' }} /> Not read
          </div>
          <button onClick={load} disabled={loading} className="p-1 text-[#525252] hover:bg-[#e0e0e0] rounded">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="text-[10px] border-collapse w-full">
          <thead>
            <tr>
              <th className="text-left py-1.5 px-2 text-[#525252] font-semibold border border-[#e0e0e0] bg-[#f4f4f4] min-w-28 sticky left-0 z-10">
                Document
              </th>
              {agents.map((a) => (
                <th
                  key={a}
                  className="text-center py-1.5 px-1 font-semibold text-[#525252] border border-[#e0e0e0] bg-[#f4f4f4]"
                  style={{ minWidth: 56, maxWidth: 80, writingMode: 'vertical-lr', transform: 'rotate(180deg)', height: 64 }}
                >
                  {a}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr key={doc.document} className="hover:bg-[#f9f9f9]">
                <td
                  className="py-1.5 px-2 text-[#161616] border border-[#e0e0e0] sticky left-0 bg-white truncate max-w-48"
                  title={doc.document}
                >
                  <span className="text-[9px] text-[#8d8d8d] mr-1">[{doc.document_type}]</span>
                  {doc.document}
                </td>
                {agents.map((a) => {
                  const read = doc.coverage[a]
                  return (
                    <td
                      key={a}
                      className="text-center border border-[#e0e0e0]"
                      style={{
                        backgroundColor: read ? '#defbe6' : '#f4f4f4',
                        width: 56,
                      }}
                      title={`${a} ${read ? 'read' : 'did not read'} ${doc.document}`}
                    >
                      {read ? (
                        <span className="text-[#24a148] font-bold">✓</span>
                      ) : (
                        <span className="text-[#a8a8a8]">·</span>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
