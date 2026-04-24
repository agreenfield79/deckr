import { get, post, getApiBaseUrl } from './client'
import type { AgentInfo, AgentRequest, AgentResponse, PipelineEvent } from '../types/agent'

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

/**
 * Run the full analysis pipeline and stream progress events.
 * Calls `onEvent` for each NDJSON line emitted by the backend.
 */
export async function runPipeline(
  sessionId: string,
  onEvent: (event: PipelineEvent) => void,
  message = '',
): Promise<void> {
  const url = `${getApiBaseUrl()}/api/agent/pipeline`
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })

  if (!resp.ok) {
    let detail = `Pipeline request failed (${resp.status})`
    try {
      const body = await resp.json()
      if (body.detail) detail = body.detail
    } catch { /* non-JSON */ }
    throw new Error(detail)
  }

  const reader = resp.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed) {
        try {
          onEvent(JSON.parse(trimmed) as PipelineEvent)
        } catch {
          // skip malformed line
        }
      }
    }
  }

  // Flush any remaining buffered content
  if (buffer.trim()) {
    try {
      onEvent(JSON.parse(buffer.trim()) as PipelineEvent)
    } catch { /* ignore */ }
  }
}
