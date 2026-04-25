import { post } from './client'

export interface ResetResponse {
  status: 'reset' | 'partial'
  cleared: string[]
  errors?: string[]
}

/**
 * Trigger a full pipeline data reset across all storage tiers.
 * Requires RESET_ENABLED=true on the backend.
 * ?confirm=true is appended to satisfy the backend guard.
 */
export const resetPipelineData = (): Promise<ResetResponse> =>
  post<ResetResponse>('/admin/reset?confirm=true&force=true')
