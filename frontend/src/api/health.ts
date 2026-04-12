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
  [key: string]: string | undefined
}

export interface HealthResponse {
  status: string
  config: HealthConfig
}

export const getHealth = (): Promise<HealthResponse> =>
  get<HealthResponse>('/health')
