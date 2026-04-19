export interface OwnershipEntry {
  name: string
  percent: number | ''
  role: string
}

export interface ManagementBio {
  name: string
  bio: string
}

export interface Guarantor {
  name: string
  relationship: string
  net_worth: string
}

export interface BorrowerProfile {
  business_name: string
  entity_type: string
  industry: string
  years_in_business: number | ''
  address: string
  ownership_structure: OwnershipEntry[]
  management_bios: ManagementBio[]
  existing_banking_relationship: string
  website: string
}

export interface LoanRequest {
  loan_amount: number | ''
  loan_type: string
  loan_purpose: string
  repayment_source: string
  interest_rate: number | ''
  term_months: number | ''
  amortization_months: number | ''
  collateral_offered: string[]
  guarantors: Guarantor[]
  desired_timing: string
}

export const emptyBorrower = (): BorrowerProfile => ({
  business_name: '',
  entity_type: '',
  industry: '',
  years_in_business: '',
  address: '',
  ownership_structure: [],
  management_bios: [],
  existing_banking_relationship: '',
  website: '',
})

export const emptyLoan = (): LoanRequest => ({
  loan_amount: '',
  loan_type: '',
  loan_purpose: '',
  repayment_source: '',
  interest_rate: '',
  term_months: '',
  amortization_months: '',
  collateral_offered: [],
  guarantors: [],
  desired_timing: '',
})
