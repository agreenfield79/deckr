import { useEffect, useRef, useState } from 'react'

export type AgentEventType = 'agent_start' | 'agent_done' | 'agent_saved'

export interface AgentEvent {
  type: AgentEventType
  agent_name: string
  elapsed_ms?: number
  saved_to?: string
  session_id?: string
  timestamp: string
}

export type AgentStatus = 'idle' | 'working' | 'saving'

export interface AgentActivityEntry {
  status: AgentStatus
  elapsed_ms?: number
  saved_to?: string
  /** Date.now() when this status was last set — used for elapsed timer */
  since: number
}

export type AgentActivityState = Record<string, AgentActivityEntry>

const SSE_BASE_URL = import.meta.env.VITE_SSE_BASE_URL ?? 'http://localhost:8000'

export function useAgentEvents() {
  const [agentActivity, setAgentActivity] = useState<AgentActivityState>({})
  const saveResetTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  useEffect(() => {
    const es = new EventSource(`${SSE_BASE_URL}/api/agent/events`)

    es.onmessage = (e: MessageEvent<string>) => {
      try {
        const event = JSON.parse(e.data) as AgentEvent
        const { type, agent_name, elapsed_ms, saved_to } = event
        const now = Date.now()

        setAgentActivity((prev) => {
          if (type === 'agent_start') {
            return {
              ...prev,
              [agent_name]: { status: 'working', since: now },
            }
          }
          if (type === 'agent_saved') {
            return {
              ...prev,
              [agent_name]: { status: 'saving', saved_to, since: now },
            }
          }
          if (type === 'agent_done') {
            return {
              ...prev,
              [agent_name]: { status: 'idle', elapsed_ms, since: now },
            }
          }
          return prev
        })

        // Auto-reset "saving" back to idle after 2.5 s so the badge doesn't stick
        if (type === 'agent_saved') {
          const existing = saveResetTimers.current.get(agent_name)
          if (existing) clearTimeout(existing)
          const t = setTimeout(() => {
            setAgentActivity((prev) => {
              const entry = prev[agent_name]
              if (entry?.status === 'saving') {
                return { ...prev, [agent_name]: { ...entry, status: 'idle' } }
              }
              return prev
            })
            saveResetTimers.current.delete(agent_name)
          }, 2500)
          saveResetTimers.current.set(agent_name, t)
        }
      } catch {
        // ignore unparseable frames (keepalive comments arrive as empty data)
      }
    }

    es.onerror = () => {
      // EventSource auto-reconnects; no action needed
    }

    return () => {
      es.close()
      // Clear any pending timers on unmount
      saveResetTimers.current.forEach((t) => clearTimeout(t))
      saveResetTimers.current.clear()
    }
  }, [])

  return { agentActivity }
}
