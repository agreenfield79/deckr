export type AgentName =
  | 'extraction'
  | 'industry'
  | 'collateral'
  | 'guarantor'
  | 'packaging'
  | 'financial'
  | 'risk'
  | 'coordination'
  | 'review'
  | 'deckr'

export interface AgentInfo {
  name: AgentName
  display_name: string
  mode: 'generate' | 'chat'
  conversational: boolean
}

export interface AgentMessage {
  role: 'user' | 'agent'
  content: string
  agent_name?: AgentName    // present on agent replies
  saved_to?: string         // populated if agent saved output to workspace
  timestamp: number
}

export interface AgentRequest {
  message: string
  agent_name: AgentName
  session_id: string
  messages: { role: string; content: string }[]
  save_to_workspace?: boolean
  save_path?: string
  action_type?: string      // routes to a specific action prompt template (e.g. "analyze_leverage")
  tools?: object[]          // reserved for Phase 15 tool calling
}

export interface AgentResponse {
  reply: string
  agent_name: AgentName
  session_id: string
  saved_to: string | null
  saved_files?: string[] | null   // all files written during a multi-save run
}

// ---------------------------------------------------------------------------
// Pipeline types — Phase 13
// ---------------------------------------------------------------------------

export interface PipelineRequest {
  session_id: string
  message?: string
}

export type PipelineEventType =
  | 'pipeline_start'
  | 'step_start'
  | 'step_done'
  | 'step_error'
  | 'pipeline_complete'

export interface PipelineEvent {
  type: PipelineEventType
  // pipeline_start
  total?: number
  // step_start / step_done / step_error
  agent?: string
  display_name?: string
  step?: number
  // step_done
  saved_to?: string | null
  elapsed_ms?: number
  reply_preview?: string
  // step_error
  error?: string
  // pipeline_complete
  steps_done?: number
  steps_failed?: number
  total_elapsed_ms?: number
}

export interface PipelineStepState {
  agent: string
  display_name: string
  status: 'pending' | 'running' | 'done' | 'error'
  saved_to?: string | null
  elapsed_ms?: number
  error?: string
}
