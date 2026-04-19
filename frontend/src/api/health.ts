import { get } from './client'

export interface HealthConfig {
  IBMCLOUD_API_KEY?: string
  WATSONX_PROJECT_ID?: string
  WATSONX_URL?: string
  WATSONX_API_VERSION?: string
  USE_ORCHESTRATE?: string
  ENABLE_EXTRACTION?: string
  WORKSPACE_ROOT?: string
  ORCHESTRATE_BASE_URL?: string
  ORCHESTRATE_API_KEY?: string
  ORCHESTRATE_AGENTS_CONFIGURED?: string
  STORAGE_BACKEND?: string
  [key: string]: string | undefined
}

export interface DbStatus {
  connected: boolean
  error?: string
  [key: string]: unknown
}

export interface HealthFeatures {
  pipeline_history: boolean
  graph_enrichment: boolean
  vector_search: boolean
  projections: boolean
  [key: string]: boolean
}

export interface HealthResponse {
  status: string
  storage_mode?: string
  config: HealthConfig
  storage?: Record<string, DbStatus>
  databases?: Record<string, DbStatus>
  features?: HealthFeatures
}

export const getHealth = (): Promise<HealthResponse> =>
  get<HealthResponse>('/health')
