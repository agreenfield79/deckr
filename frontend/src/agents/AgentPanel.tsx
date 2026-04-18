import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Send, Loader2, Trash2 } from 'lucide-react'
import { useAgent } from './useAgent'
import { useAgentEvents } from './useAgentEvents'
import AgentSelector from './AgentSelector'
import AgentMessageItem from './AgentMessage'
import AgentActions from './AgentActions'
import AgentOffice from './AgentOffice'
import { useProject } from '../context/ProjectContext'
import { useToast } from '../context/ToastContext'
import { getHealth } from '../api/health'

export default function AgentPanel() {
  const { refreshTree, writeFile } = useProject()
  const { success: toastSuccess, error: toastError } = useToast()
  const { agentActivity } = useAgentEvents()
  const {
    agents,
    selectedAgent,
    setSelectedAgent,
    messages,
    isLoading,
    runningAgent,
    sendMessage,
    runAgent,
    runPipeline,
    isPipelineRunning,
    pipelineSteps,
    pipelineTotalMs,
    clearHistory,
  } = useAgent()

  const [input, setInput] = useState('')
  const [orchestrateActive, setOrchestrateActive] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Check health on mount to determine if Orchestrate memory is active
  useEffect(() => {
    getHealth()
      .then((h) => {
        setOrchestrateActive(h.config?.USE_ORCHESTRATE === 'true')
      })
      .catch(() => {/* offline — memory stays inactive */})
  }, [])

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || isLoading) return
    setInput('')
    await sendMessage(text)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleRunAgent = async (agentName: string) => {
    const res = await runAgent(agentName)
    await refreshTree()
    if (res?.saved_files && res.saved_files.length > 1) {
      toastSuccess(
        `Saved to ${res.saved_to} — ${res.saved_files.length - 1} additional analyses queued`,
      )
    } else if (res?.saved_to) {
      toastSuccess(`Saved to ${res.saved_to}`)
    }
  }

  const handleRunPipeline = async () => {
    await runPipeline()
    await refreshTree()
  }

  const handleSaveToWorkspace = async (content: string, agentName: string) => {
    const savePath = `Agent Notes/${agentName}_notes.md`
    try {
      await writeFile(savePath, content)
      await refreshTree()
      toastSuccess(`Saved to ${savePath}`)
    } catch {
      toastError('Failed to save to workspace')
    }
  }

  const activeAgentLabel =
    selectedAgent === 'packaging'
      ? 'Deckr (auto)'
      : agents.find((a) => a.name === selectedAgent)?.display_name ?? selectedAgent

  return (
    <div className="h-full flex flex-col bg-[#f4f4f4] border-l border-[#e0e0e0] overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-[#e0e0e0] flex items-center justify-between shrink-0">
        <span className="text-xs font-semibold text-[#525252] uppercase tracking-wider">
          Agent Panel
        </span>
        <div className="flex items-center gap-2">
          {/* Memory status indicator — reflects live Orchestrate state */}
          <span
            title={orchestrateActive ? 'Memory active — IBM watsonx Orchestrate' : 'Memory inactive — activates when USE_ORCHESTRATE=true'}
            className={`text-[10px] px-1.5 py-0.5 rounded font-mono cursor-default transition-colors ${
              orchestrateActive
                ? 'text-[#198038] bg-[#defbe6]'
                : 'text-[#a8a8a8] bg-[#e0e0e0]'
            }`}
          >
            {orchestrateActive ? 'Memory ●' : 'Memory ○'}
          </span>
          <button
            onClick={clearHistory}
            title="Clear conversation"
            className="p-1 text-[#6f6f6f] hover:text-[#da1e28] rounded transition-colors"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* Agent Selector */}
      <div className="shrink-0">
        <AgentSelector
          agents={agents}
          selected={selectedAgent}
          onSelect={setSelectedAgent}
        />
      </div>

      {/* Agent Office — real-time status cards */}
      <AgentOffice
        agentActivity={agentActivity}
        pipelineSteps={pipelineSteps}
        isPipelineRunning={isPipelineRunning}
        pipelineTotalMs={pipelineTotalMs}
      />

      {/* Message list */}
      <div className="flex-1 overflow-y-auto py-2 space-y-0.5">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full px-4">
            <p className="text-xs text-[#a8a8a8] text-center leading-relaxed">
              Select an agent above, or click{' '}
              <span className="font-semibold text-[#6f6f6f]">Run</span> to start.
              <br />
              <span className="text-[10px]">Active: {activeAgentLabel}</span>
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <AgentMessageItem
              key={msg.timestamp}
              message={msg}
              onSave={handleSaveToWorkspace}
            />
          ))
        )}

        {/* Loading skeleton */}
        {isLoading && (
          <div className="flex flex-col px-3 py-1 gap-1">
            <span className="text-[10px] font-semibold text-[#0f62fe] bg-[#edf4ff] px-1.5 py-0.5 rounded w-fit">
              {activeAgentLabel}
            </span>
            <div className="bg-white border border-[#e0e0e0] rounded-lg px-3 py-2 flex items-center gap-2">
              <Loader2 size={12} className="animate-spin text-[#0f62fe] shrink-0" />
              <span className="text-xs text-[#6f6f6f]">Thinking…</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Quick Run actions */}
      <div className="shrink-0">
        <AgentActions
          agents={agents}
          runningAgent={runningAgent}
          onRun={handleRunAgent}
          isPipelineRunning={isPipelineRunning}
          pipelineSteps={pipelineSteps}
          onRunPipeline={handleRunPipeline}
        />
      </div>

      {/* Input area */}
      <div className="px-3 py-3 border-t border-[#e0e0e0] shrink-0">
        <div className="flex items-end gap-2 bg-white border border-[#c6c6c6] rounded px-3 py-2 focus-within:border-[#0f62fe] focus-within:ring-1 focus-within:ring-[#0f62fe] transition-colors">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Message ${activeAgentLabel}… (Enter to send)`}
            rows={1}
            className="flex-1 text-xs text-[#161616] bg-transparent resize-none outline-none leading-relaxed placeholder:text-[#a8a8a8] max-h-32 overflow-y-auto"
            style={{ fieldSizing: 'content' } as React.CSSProperties}
            disabled={isLoading || !!runningAgent || isPipelineRunning}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading || !!runningAgent || isPipelineRunning}
            className="shrink-0 p-1 text-[#0f62fe] hover:text-[#0043ce] disabled:text-[#c6c6c6] transition-colors"
            title="Send message"
          >
            {isLoading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
          </button>
        </div>
        <p className="text-[10px] text-[#a8a8a8] mt-1">
          Shift+Enter for newline
        </p>
      </div>
    </div>
  )
}
