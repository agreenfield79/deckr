import { useState, useEffect, useRef, useCallback } from 'react'
import { Upload, X, FileText, Loader2, Database } from 'lucide-react'
import clsx from 'clsx'
import { uploadFile, listUploads, type UploadedFile } from '../api/upload'
import { useProject } from '../context/ProjectContext'
import { useToast } from '../context/ToastContext'
import * as workspaceApi from '../api/workspace'
import { getDocumentMetadata, getCurrentDeal, type DocumentMetadata } from '../api/pipelineRuns'
import DocumentCoverageHeatmap from '../components/DocumentCoverageHeatmap'

// ---------------------------------------------------------------------------
// Zone definitions
// ---------------------------------------------------------------------------
interface ZoneDef {
  category: string
  folder: string
  label: string
  description: string
  accepts: string
}

const ZONES: ZoneDef[] = [
  {
    category: 'Financial Statements',
    folder: 'Financials',
    label: 'Financial Statements',
    description: '3 years of P&L, balance sheets, cash flow statements',
    accepts: '.pdf,.xlsx,.xls,.csv',
  },
  {
    category: 'Tax Returns',
    folder: 'Tax Returns',
    label: 'Tax Returns',
    description: 'Business and personal returns — 3 years',
    accepts: '.pdf',
  },
  {
    category: 'Interim Financials',
    folder: 'Financials/interim',
    label: 'Interim Financials',
    description: 'YTD income statement and balance sheet',
    accepts: '.pdf,.xlsx,.xls,.csv',
  },
  {
    category: 'Collateral Docs',
    folder: 'Collateral',
    label: 'Collateral Docs',
    description: 'Appraisals, titles, environmental reports',
    accepts: '.pdf,.docx,.doc',
  },
  {
    category: 'Guarantor Financials',
    folder: 'Guarantors',
    label: 'Guarantor Financials',
    description: 'Personal financial statements and schedules',
    accepts: '.pdf,.xlsx,.xls',
  },
  {
    category: 'Bank Statements',
    folder: 'Financials/bank_statements',
    label: 'Bank Statements',
    description: '6–12 months of business bank statements',
    accepts: '.pdf,.csv',
  },
  {
    category: 'Rent Roll',
    folder: 'Collateral/rent_roll',
    label: 'Rent Roll',
    description: 'Current rent roll for income-producing properties',
    accepts: '.pdf,.xlsx,.xls,.csv',
  },
  {
    category: 'Other',
    folder: 'Other',
    label: 'Other Documents',
    description: 'Leases, licenses, entity docs, other materials',
    accepts: '*',
  },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

// ---------------------------------------------------------------------------
// UploadZone
// ---------------------------------------------------------------------------
interface UploadZoneProps {
  zone: ZoneDef
  onUploaded: () => void
}

function UploadZone({ zone, onUploaded }: UploadZoneProps) {
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const toast = useToast()
  const { refreshTree } = useProject()

  const loadFiles = useCallback(async () => {
    try {
      const list = await listUploads(zone.folder)
      setFiles(list)
    } catch {
      setFiles([])
    }
  }, [zone.folder])

  useEffect(() => {
    loadFiles()
  }, [loadFiles])

  const handleFiles = async (fileList: FileList) => {
    if (fileList.length === 0) return
    setUploading(true)
    let successCount = 0
    for (const file of Array.from(fileList)) {
      try {
        await uploadFile(file, zone.category)
        successCount++
      } catch (e) {
        toast.error(`Failed to upload ${file.name}: ${e instanceof Error ? e.message : 'Unknown error'}`)
      }
    }
    setUploading(false)
    if (successCount > 0) {
      toast.success(
        successCount === 1
          ? `Uploaded ${fileList[0].name}`
          : `Uploaded ${successCount} files to ${zone.label}`,
      )
      await loadFiles()
      await refreshTree()
      onUploaded()
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files) handleFiles(e.dataTransfer.files)
  }

  const handleRemove = async (path: string) => {
    try {
      await workspaceApi.deleteFile(path)
      await loadFiles()
      await refreshTree()
    } catch {
      toast.error('Could not remove file.')
    }
  }

  return (
    <div className="border border-[#e0e0e0] rounded bg-white flex flex-col">
      {/* Zone header */}
      <div className="px-3 py-2 border-b border-[#e0e0e0] bg-[#f4f4f4]">
        <p className="text-xs font-semibold text-[#161616]">{zone.label}</p>
        <p className="text-xs text-[#8d8d8d] mt-0.5">{zone.description}</p>
      </div>

      {/* Drop area */}
      <div
        className={clsx(
          'mx-3 mt-2 mb-2 rounded border-2 border-dashed transition-colors cursor-pointer flex flex-col items-center justify-center py-4 gap-1 select-none',
          dragOver
            ? 'border-[#0f62fe] bg-[#edf4ff]'
            : 'border-[#c6c6c6] hover:border-[#8d8d8d] hover:bg-[#f4f4f4]',
        )}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={zone.accepts}
          className="hidden"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
        {uploading ? (
          <Loader2 size={18} className="text-[#0f62fe] animate-spin" />
        ) : (
          <Upload size={18} className={dragOver ? 'text-[#0f62fe]' : 'text-[#8d8d8d]'} />
        )}
        <span className="text-xs text-[#525252]">
          {uploading ? 'Uploading…' : 'Drop files or click to browse'}
        </span>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="mx-3 mb-2 space-y-1">
          {files.map((f) => (
            <div
              key={f.path}
              className="flex items-center gap-1.5 px-2 py-1.5 bg-[#f4f4f4] rounded text-xs"
            >
              <FileText size={12} className="text-[#525252] shrink-0" />
              <span className="flex-1 truncate text-[#161616]">{f.name}</span>
              <span className="text-[#8d8d8d] shrink-0">{formatSize(f.size)}</span>
              <span className="text-[#8d8d8d] shrink-0 hidden sm:block">
                {formatDate(f.modified)}
              </span>
              {f.extracted && (
                <span className="px-1.5 py-0.5 bg-[#defbe6] text-[#0e6027] rounded text-[10px] font-medium shrink-0">
                  Extracted
                </span>
              )}
              <button
                className="p-0.5 text-[#8d8d8d] hover:text-[#da1e28] transition-colors shrink-0"
                title="Remove"
                onClick={() => handleRemove(f.path)}
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// DocumentsTab
// ---------------------------------------------------------------------------
export default function DocumentsTab() {
  const [uploadCount, setUploadCount] = useState(0)
  const [docMeta, setDocMeta]         = useState<DocumentMetadata[]>([])

  useEffect(() => {
    getCurrentDeal().then((deal) => {
      if (deal.deal_id) {
        getDocumentMetadata(deal.deal_id)
          .then((r) => setDocMeta(r.documents ?? []))
          .catch(() => setDocMeta([]))
      }
    }).catch(() => {})
  }, [uploadCount])


  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-6">
        <div className="mb-6">
          <h2 className="text-base font-semibold text-[#161616]">Document Upload Center</h2>
          <p className="mt-1 text-xs text-[#525252]">
            Upload supporting documents into each category. Files are saved directly to your
            workspace and will be available to AI agents for analysis.
          </p>
        </div>

        {/* MongoDB document index — agent read badges */}
        {docMeta.length > 0 && (
          <div className="mb-6 border border-[#e0e0e0] rounded bg-white overflow-hidden">
            <div className="px-3 py-2 bg-[#f4f4f4] border-b border-[#e0e0e0] flex items-center gap-2">
              <Database size={12} className="text-[#525252]" />
              <span className="text-xs font-semibold text-[#161616]">Document Index</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#e0e0e0] text-[#525252]">
                {docMeta.length} indexed
              </span>
            </div>
            <div className="divide-y divide-[#f4f4f4]">
              {docMeta.map((doc) => (
                <div key={doc.document_id} className="flex items-center gap-2 px-3 py-2 text-xs">
                  <FileText size={12} className="text-[#525252] shrink-0" />
                  <span className="flex-1 truncate text-[#161616]">{doc.file_name}</span>
                  <span className="text-[10px] text-[#8d8d8d] shrink-0">{doc.document_type}</span>
                  {doc.agents_read && doc.agents_read.length > 0
                    ? doc.agents_read.map((a) => (
                        <span key={a} className="text-[10px] px-1.5 py-0.5 rounded bg-[#edf4ff] text-[#0043ce] shrink-0">
                          {a}
                        </span>
                      ))
                    : (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#f4f4f4] text-[#a8a8a8] shrink-0">
                          not yet read
                        </span>
                      )
                  }
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {ZONES.map((zone) => (
            <UploadZone
              key={zone.category}
              zone={zone}
              onUploaded={() => setUploadCount((c) => c + 1)}
            />
          ))}
        </div>

        {/* Document Coverage Heatmap — agents × documents read matrix */}
        <DocumentCoverageHeatmap />
      </div>
    </div>
  )
}
