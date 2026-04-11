import { useState, useCallback, useEffect, useRef } from 'react'
import * as agentApi from '../api/agent'
import { useSession } from '../hooks/useSession'
import type { AgentInfo, AgentMessage, AgentName, AgentResponse } from '../types/agent'

export function useAgent() {
  const { sessionId } = useSession()
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [selectedAgent, setSelectedAgent] = useState<AgentName>('packaging')
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [runningAgent, setRunningAgent] = useState<string | null>(null)

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

  const clearHistory = useCallback(() => setMessages([]), [])

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
    clearHistory,
  }
}
