import { get } from './client'

export interface HealthResponse {
  status: string
  configured: boolean
  watsonx_url?: string
  project_id_set?: boolean
  api_key_set?: boolean
}

export const getHealth = (): Promise<HealthResponse> =>
  get<HealthResponse>('/health')
