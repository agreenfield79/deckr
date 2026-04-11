import { Bookmark } from 'lucide-react'
import MarkdownViewer from '../editor/MarkdownViewer'
import type { AgentMessage } from '../types/agent'

const AGENT_LABELS: Record<string, string> = {
  packaging:   'Packaging Agent',
  financial:   'Financial Agent',
  risk:        'SLACR Risk Agent',
  coordination: 'Coordination Agent',
  review:      'Review Agent',
}

interface AgentMessageItemProps {
  message: AgentMessage
  onSave?: (content: string, agentName: string) => void
}

export default function AgentMessageItem({ message, onSave }: AgentMessageItemProps) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end px-3 py-1">
        <div className="max-w-[80%] bg-[#0f62fe] text-white text-xs rounded-lg px-3 py-2 leading-relaxed">
          {message.content}
        </div>
      </div>
    )
  }

  const agentLabel = message.agent_name
    ? AGENT_LABELS[message.agent_name] ?? message.agent_name
    : 'Agent'

  return (
    <div className="flex flex-col px-3 py-1 gap-1">
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] font-semibold text-[#0f62fe] bg-[#edf4ff] px-1.5 py-0.5 rounded">
          {agentLabel}
        </span>
        {message.saved_to && (
          <span className="text-[10px] text-[#6f6f6f]">
            → saved to{' '}
            <span className="font-mono text-[#161616]">{message.saved_to}</span>
          </span>
        )}
      </div>
      <div className="max-w-full bg-white border border-[#e0e0e0] rounded-lg px-3 py-2 text-xs leading-relaxed relative group">
        <MarkdownViewer content={message.content} />
        {onSave && message.agent_name && (
          <button
            onClick={() => onSave(message.content, message.agent_name!)}
            title="Save to workspace"
            className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 text-[#6f6f6f] hover:text-[#0f62fe]"
          >
            <Bookmark size={12} />
          </button>
        )}
      </div>
    </div>
  )
}
