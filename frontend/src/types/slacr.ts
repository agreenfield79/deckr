export interface SlacrInput {
  strength: number        // 1=excellent, 5=high risk
  leverage: number
  ability_to_repay: number
  collateral: number
  risk_factors: number
  notes: Record<string, string>
}

export interface SlacrOutput {
  weighted_score: number
  rating: string
  decision: string
  mitigants: string[]
  ai_narrative: string
  input: SlacrInput
}

export const SLACR_DIMENSIONS: {
  field: keyof Omit<SlacrInput, 'notes'>
  label: string
  weight: string
  description: string
}[] = [
  {
    field: 'strength',
    label: 'Sponsor / Management',
    weight: '20%',
    description: 'Experience, track record, succession planning',
  },
  {
    field: 'leverage',
    label: 'Leverage & Capitalization',
    weight: '20%',
    description: 'D/E ratio, D/EBITDA, equity cushion',
  },
  {
    field: 'ability_to_repay',
    label: 'Ability to Repay',
    weight: '25%',
    description: 'DSCR, cash flow consistency, debt service coverage',
  },
  {
    field: 'collateral',
    label: 'Collateral Quality',
    weight: '15%',
    description: 'LTV, lien position, asset liquidity and diversification',
  },
  {
    field: 'risk_factors',
    label: 'Industry & Market Risk',
    weight: '20%',
    description: 'Sector cyclicality, competitive position, regulatory exposure',
  },
]

export const SCORE_LABELS: Record<number, { label: string; color: string }> = {
  1: { label: 'Excellent', color: '#24a148' },
  2: { label: 'Good',      color: '#198038' },
  3: { label: 'Acceptable', color: '#f1c21b' },
  4: { label: 'Weak',      color: '#ff832b' },
  5: { label: 'High Risk', color: '#da1e28' },
}

export function getRatingColor(score: number): string {
  if (score <= 1.75) return '#24a148'
  if (score <= 2.50) return '#f1c21b'
  if (score <= 3.25) return '#ff832b'
  return '#da1e28'
}
