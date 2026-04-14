import { getFile } from './workspace'

export interface FiscalYearValues {
  [year: string]: number | null
}

export interface ExtractedFinancials {
  company: string
  document_type: string
  fiscal_years: string[]
  income_statement: {
    revenue: FiscalYearValues
    gross_profit: FiscalYearValues
    ebitda: FiscalYearValues
    operating_income: FiscalYearValues
    net_income: FiscalYearValues
    interest_expense: FiscalYearValues
    depreciation_amortization: FiscalYearValues
  }
  balance_sheet: {
    total_assets: FiscalYearValues
    total_liabilities: FiscalYearValues
    total_equity: FiscalYearValues
    cash: FiscalYearValues
    current_assets: FiscalYearValues
    current_liabilities: FiscalYearValues
    total_debt: FiscalYearValues
    long_term_debt: FiscalYearValues
  }
  cash_flow_statement: {
    operating_cash_flow: FiscalYearValues
    capex: FiscalYearValues
    free_cash_flow: FiscalYearValues
  }
  metadata: {
    source_files: string[]
    missing_fields: string[]
    extracted_at: string
  }
}

export async function getExtractedFinancials(): Promise<ExtractedFinancials | null> {
  try {
    const res = await getFile('Financials/extracted_data.json')
    if (!res.content) return null
    return JSON.parse(res.content) as ExtractedFinancials
  } catch {
    return null
  }
}
