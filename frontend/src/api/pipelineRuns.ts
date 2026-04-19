import { get } from './client'

export interface PipelineStage {
  agent_name: string
  stage_order: number
  status: 'complete' | 'error' | 'skipped'
  elapsed_ms: number
  saved_to: string | null
  completed_at: string
}

export interface PipelineRun {
  pipeline_run_id: string
  deal_id: string
  workspace_id: string
  status: 'running' | 'complete' | 'partial' | 'error'
  started_at: string
  completed_at?: string
  total_elapsed_ms?: number
  total_stages?: number
  stages: PipelineStage[]
  source?: string
}

export interface PipelineHistoryResponse {
  runs: PipelineRun[]
  count: number
  error?: string
}

export async function getPipelineHistory(
  dealId?: string,
  limit = 20,
): Promise<PipelineHistoryResponse> {
  const params = new URLSearchParams()
  if (dealId) params.set('deal_id', dealId)
  params.set('limit', String(limit))
  return get<PipelineHistoryResponse>(`/status/pipeline-history?${params.toString()}`)
}

export interface CurrentDeal {
  deal_id: string | null
  workspace_id: string | null
}

export async function getCurrentDeal(): Promise<CurrentDeal> {
  return get<CurrentDeal>('/workspace/current-deal')
}

export interface DocumentMetadata {
  document_id: string
  file_name: string
  file_path: string
  document_type: string
  deal_id: string | null
  indexed_at: string
  agents_read?: string[]
}

export interface DocumentMetadataResponse {
  documents: DocumentMetadata[]
  count: number
}

export async function getDocumentMetadata(
  dealId?: string,
): Promise<DocumentMetadataResponse> {
  const params = dealId ? `?deal_id=${encodeURIComponent(dealId)}` : ''
  return get<DocumentMetadataResponse>(`/workspace/document-metadata${params}`)
}
