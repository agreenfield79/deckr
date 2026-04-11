import { CheckCircle, Clock, ArrowRight, RefreshCw } from 'lucide-react'
import { useStatus } from '../hooks/useStatus'
import type { TabId } from './TabBar'

interface StatusTabProps {
  onNavigate: (tab: TabId) => void
}

function motivate(percentage: number): string {
  if (percentage === 100) return 'Your package is complete! Review the deck and submit for credit committee review.'
  if (percentage >= 75)   return `Your package is ${percentage}% complete — almost there!`
  if (percentage >= 50)   return `Your package is ${percentage}% complete. Here's what's left:`
  if (percentage >= 25)   return `Your package is ${percentage}% complete. Keep going!`
  return `Your package is ${percentage}% complete. Let's get started!`
}

export default function StatusTab({ onNavigate }: StatusTabProps) {
  const { items, percentage, loading, refresh } = useStatus()

  const completeCount = items.filter((i) => i.complete).length

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5">
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h2 className="text-sm font-semibold text-[#161616]">Package Status</h2>
          <p className="text-xs text-[#6f6f6f] mt-1 max-w-sm leading-relaxed">
            {motivate(percentage)}
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          title="Re-check status"
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-[#525252] border border-[#c6c6c6] bg-white hover:bg-[#e0e0e0] rounded transition-colors disabled:opacity-50 shrink-0"
        >
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] font-medium text-[#525252] uppercase tracking-wider">
            Overall Completeness
          </span>
          <span className="text-xs font-semibold text-[#161616]">{percentage}%</span>
        </div>
        <div className="h-2.5 bg-[#e0e0e0] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${percentage}%`,
              backgroundColor:
                percentage === 100 ? '#24a148' : percentage >= 75 ? '#0f62fe' : '#0f62fe',
            }}
          />
        </div>
        <div className="flex justify-between mt-1.5">
          <span className="text-[10px] text-[#6f6f6f]">
            {completeCount} of {items.length} items complete
          </span>
          {percentage === 100 && (
            <span className="text-[10px] text-[#24a148] font-semibold">
              ✓ Ready for review
            </span>
          )}
        </div>
      </div>

      {/* Checklist */}
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.label}
            className={`flex items-center gap-3 px-3.5 py-2.5 rounded border transition-colors ${
              item.complete
                ? 'bg-[#defbe6] border-[#a7f0ba]'
                : 'bg-white border-[#e0e0e0] hover:border-[#c6c6c6]'
            }`}
          >
            {item.complete ? (
              <CheckCircle size={15} className="shrink-0 text-[#24a148]" />
            ) : (
              <Clock size={15} className="shrink-0 text-[#f1c21b]" />
            )}

            <span
              className={`text-xs flex-1 ${
                item.complete ? 'text-[#198038] font-medium' : 'text-[#161616]'
              }`}
            >
              {item.label}
            </span>

            {/* Navigation action for incomplete items */}
            {!item.complete && item.tab && item.action && (
              <button
                onClick={() => onNavigate(item.tab as TabId)}
                className="flex items-center gap-1 text-[10px] text-[#0f62fe] hover:text-[#0043ce] hover:underline shrink-0 transition-colors"
              >
                {item.action}
                <ArrowRight size={10} />
              </button>
            )}
            {!item.complete && !item.tab && item.action && (
              <span className="text-[10px] text-[#a8a8a8] shrink-0 italic">
                {item.action}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
