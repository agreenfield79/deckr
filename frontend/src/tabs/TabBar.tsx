import clsx from 'clsx'

export type TabId =
  | 'onboarding'
  | 'loan'
  | 'documents'
  | 'notes'
  | 'status'
  | 'interpret'
  | 'underwriting'
  | 'memo'
  | 'proposal'
  | 'deckr'

interface Tab {
  id: TabId
  label: string
  disabled?: boolean
}

const TABS: Tab[] = [
  { id: 'onboarding',   label: 'Onboarding' },
  { id: 'loan',         label: 'Loan Request' },
  { id: 'documents',    label: 'Documents' },
  { id: 'notes',        label: 'Notes' },
  { id: 'status',       label: 'Status' },
  { id: 'interpret',    label: 'Interpret',    disabled: true },
  { id: 'underwriting', label: 'Underwriting' },
  { id: 'memo',         label: 'Memo' },
  { id: 'proposal',     label: 'Proposal' },
  { id: 'deckr',        label: 'Deckr' },
]

interface TabBarProps {
  active: TabId
  onChange: (id: TabId) => void
}

export default function TabBar({ active, onChange }: TabBarProps) {
  return (
    <div className="flex items-end gap-0 border-b border-[#e0e0e0] px-4 shrink-0 overflow-x-auto">
      {TABS.map((tab) =>
        tab.disabled ? (
          <span
            key={tab.id}
            title="Coming Soon"
            className="px-3 py-2.5 text-xs font-medium whitespace-nowrap border-b-2 border-transparent text-[#a8a8a8] cursor-not-allowed select-none -mb-px"
          >
            {tab.label}
          </span>
        ) : (
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
        ),
      )}
    </div>
  )
}
