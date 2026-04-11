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
  tools?: object[]          // reserved for Phase 13 tool calling
}

export interface AgentResponse {
  reply: string
  agent_name: AgentName
  session_id: string
  saved_to: string | null
}
