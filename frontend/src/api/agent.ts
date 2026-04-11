import { get, post } from './client'
import type { AgentInfo, AgentRequest, AgentResponse } from '../types/agent'

export const getRegistry = (): Promise<AgentInfo[]> =>
  get<AgentInfo[]>('/agent/registry')

export const sendMessage = (
  agentName: string,
  request: AgentRequest,
): Promise<AgentResponse> =>
  post<AgentResponse>(`/agent/${agentName}`, request)

export const runAgent = (
  agentName: string,
  sessionId: string,
  message = '',
): Promise<AgentResponse> =>
  post<AgentResponse>(`/agent/${agentName}/run`, {
    message,
    agent_name: agentName,
    session_id: sessionId,
    messages: [],
  })
