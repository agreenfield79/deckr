export type AgentName =
  | 'packaging'
  | 'financial'
  | 'risk'
  | 'coordination'
  | 'review'

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
  tools?: object[]          // reserved for Phase 13 tool calling
}

export interface AgentResponse {
  reply: string
  agent_name: AgentName
  session_id: string
  saved_to: string | null
  saved_files?: string[] | null   // all files written during a multi-save run
}
