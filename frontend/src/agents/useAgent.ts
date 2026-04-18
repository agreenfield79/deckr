import { useState, useCallback, useEffect, useRef } from 'react'
import * as agentApi from '../api/agent'
import { useSession } from '../hooks/useSession'
import type { AgentInfo, AgentMessage, AgentName, AgentResponse, PipelineEvent, PipelineStepState } from '../types/agent'

// Pipeline sequence mirrors PIPELINE_SEQUENCE in agent_service.py
const PIPELINE_AGENTS = ['extraction', 'financial', 'industry', 'collateral', 'guarantor', 'risk', 'packaging', 'review', 'deckr']
const PIPELINE_DISPLAY: Record<string, string> = {
  extraction: 'Financial Data Extraction Agent',
  financial:  'Financial Analysis Agent',
  industry:   'Industry Analysis Agent',
  collateral: 'Collateral Agent',
  guarantor:  'Guarantor Agent',
  risk:       'SLACR Risk Agent',
  packaging:  'Packaging Agent',
  review:     'Review Agent',
  deckr:      'Deckr Agent',
}

export function useAgent() {
  const { sessionId } = useSession()
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [selectedAgent, setSelectedAgent] = useState<AgentName>('packaging')
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [runningAgent, setRunningAgent] = useState<string | null>(null)
  const [isPipelineRunning, setIsPipelineRunning] = useState(false)
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStepState[]>([])
  const [pipelineTotalMs, setPipelineTotalMs] = useState<number | null>(null)

  // Keep a ref for messages so callbacks always have the latest value
  const messagesRef = useRef(messages)
  messagesRef.current = messages

  useEffect(() => {
    agentApi.getRegistry().then(setAgents).catch(() => {})
  }, [])

  const sendMessage = useCallback(
    async (text: string) => {
      const userMsg: AgentMessage = {
        role: 'user',
        content: text,
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, userMsg])
      setIsLoading(true)

      try {
        const history = messagesRef.current.map((m) => ({
          role: m.role === 'user' ? 'user' : 'assistant',
          content: m.content,
        }))
        const res = await agentApi.sendMessage(selectedAgent, {
          message: text,
          agent_name: selectedAgent,
          session_id: sessionId,
          messages: [...history, { role: 'user', content: text }],
        })
        const agentMsg: AgentMessage = {
          role: 'agent',
          content: res.reply,
          agent_name: selectedAgent,
          saved_to: res.saved_to ?? undefined,
          timestamp: Date.now(),
        }
        setMessages((prev) => [...prev, agentMsg])
      } catch (err) {
        const detail =
          err instanceof Error ? err.message : 'AI is temporarily unavailable.'
        const errMsg: AgentMessage = {
          role: 'agent',
          content: `⚠️ ${detail}`,
          agent_name: selectedAgent,
          timestamp: Date.now(),
        }
        setMessages((prev) => [...prev, errMsg])
      } finally {
        setIsLoading(false)
      }
    },
    [selectedAgent, sessionId],
  )

  const runAgent = useCallback(
    async (agentName: string): Promise<AgentResponse | null> => {
      setRunningAgent(agentName)
      try {
        const res = await agentApi.runAgent(agentName, sessionId)
        const resultMsg: AgentMessage = {
          role: 'agent',
          content: res.reply,
          agent_name: agentName as AgentName,
          saved_to: res.saved_to ?? undefined,
          timestamp: Date.now(),
        }
        setMessages((prev) => [...prev, resultMsg])
        return res
      } catch (err) {
        const detail =
          err instanceof Error ? err.message : 'Agent run failed.'
        const errMsg: AgentMessage = {
          role: 'agent',
          content: `⚠️ ${detail}`,
          agent_name: agentName as AgentName,
          timestamp: Date.now(),
        }
        setMessages((prev) => [...prev, errMsg])
        return null
      } finally {
        setRunningAgent(null)
      }
    },
    [sessionId],
  )

  const runPipeline = useCallback(async (): Promise<void> => {
    setIsPipelineRunning(true)

    // Initialise all steps as pending
    const initialSteps: PipelineStepState[] = PIPELINE_AGENTS.map((agent) => ({
      agent,
      display_name: PIPELINE_DISPLAY[agent] ?? agent,
      status: 'pending',
    }))
    setPipelineSteps(initialSteps)
    setPipelineTotalMs(null)

    // Announce pipeline start in chat
    setMessages((prev) => [
      ...prev,
      {
        role: 'agent',
        content: '▶ Running full analysis pipeline…',
        agent_name: 'packaging' as AgentName,
        timestamp: Date.now(),
      },
    ])

    try {
      await agentApi.runPipeline(sessionId, (event: PipelineEvent) => {
        if (event.type === 'step_start' && event.agent) {
          setPipelineSteps((prev) =>
            prev.map((s) =>
              s.agent === event.agent ? { ...s, status: 'running' } : s,
            ),
          )
        } else if (event.type === 'step_done' && event.agent) {
          setPipelineSteps((prev) =>
            prev.map((s) =>
              s.agent === event.agent
                ? { ...s, status: 'done', saved_to: event.saved_to, elapsed_ms: event.elapsed_ms }
                : s,
            ),
          )
          // Add a brief completion note per step
          const display = PIPELINE_DISPLAY[event.agent] ?? event.agent
          const savedNote = event.saved_to ? ` → saved to \`${event.saved_to}\`` : ''
          const msNote = event.elapsed_ms ? ` (${(event.elapsed_ms / 1000).toFixed(1)}s)` : ''
          setMessages((prev) => [
            ...prev,
            {
              role: 'agent',
              content: `✓ ${display} complete${savedNote}${msNote}`,
              agent_name: event.agent as AgentName,
              saved_to: event.saved_to ?? undefined,
              timestamp: Date.now(),
            },
          ])
        } else if (event.type === 'step_error' && event.agent) {
          setPipelineSteps((prev) =>
            prev.map((s) =>
              s.agent === event.agent
                ? { ...s, status: 'error', error: event.error }
                : s,
            ),
          )
          const display = PIPELINE_DISPLAY[event.agent] ?? event.agent
          setMessages((prev) => [
            ...prev,
            {
              role: 'agent',
              content: `⚠️ ${display} failed — ${event.error ?? 'unknown error'}`,
              agent_name: event.agent as AgentName,
              timestamp: Date.now(),
            },
          ])
        } else if (event.type === 'pipeline_complete') {
          const totalSec = event.total_elapsed_ms
            ? ` in ${(event.total_elapsed_ms / 1000).toFixed(0)}s`
            : ''
          const failNote =
            (event.steps_failed ?? 0) > 0
              ? ` (${event.steps_failed} step(s) failed)`
              : ''
          if (event.total_elapsed_ms) {
            setPipelineTotalMs(event.total_elapsed_ms)
          }
          setMessages((prev) => [
            ...prev,
            {
              role: 'agent',
              content: `✅ Pipeline complete — ${event.steps_done ?? 0}/${event.steps_done! + (event.steps_failed ?? 0)} steps succeeded${totalSec}${failNote}`,
              agent_name: 'packaging' as AgentName,
              timestamp: Date.now(),
            },
          ])
        }
      })
    } catch (err) {
      const detail = err instanceof Error ? err.message : 'Pipeline failed.'
      setMessages((prev) => [
        ...prev,
        {
          role: 'agent',
          content: `⚠️ Pipeline error — ${detail}`,
          agent_name: 'packaging' as AgentName,
          timestamp: Date.now(),
        },
      ])
    } finally {
      setIsPipelineRunning(false)
    }
  }, [sessionId])

  const clearHistory = useCallback(() => {
    setMessages([])
    setPipelineSteps([])
  }, [])

  return {
    agents,
    selectedAgent,
    setSelectedAgent,
    messages,
    isLoading,
    runningAgent,
    sessionId,
    sendMessage,
    runAgent,
    runPipeline,
    isPipelineRunning,
    pipelineSteps,
    pipelineTotalMs,
    clearHistory,
  }
}
