import clsx from 'clsx'

export type TabId = 'onboarding' | 'loan' | 'documents' | 'research' | 'deck' | 'status' | 'slacr'

interface Tab {
  id: TabId
  label: string
}

const TABS: Tab[] = [
  { id: 'onboarding', label: 'Onboarding' },
  { id: 'loan', label: 'Loan Request' },
  { id: 'documents', label: 'Documents' },
  { id: 'research', label: 'Research' },
  { id: 'deck', label: 'Deck' },
  { id: 'slacr', label: 'SLACR Score' },
  { id: 'status', label: 'Status' },
]

interface TabBarProps {
  active: TabId
  onChange: (id: TabId) => void
}

export default function TabBar({ active, onChange }: TabBarProps) {
  return (
    <div className="flex items-end gap-0 border-b border-[#e0e0e0] px-4 shrink-0 overflow-x-auto">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={clsx(
            'px-3 py-2.5 text-xs font-medium whitespace-nowrap transition-colors border-b-2 -mb-px',
            active === tab.id
              ? 'text-[#0f62fe] border-[#0f62fe]'
              : 'text-[#525252] border-transparent hover:text-[#161616] hover:border-[#c6c6c6]',
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
