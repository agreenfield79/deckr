import { useState, useEffect } from 'react'
import FormField from './FormField'
import { getLoan, saveLoan } from '../api/forms'
import { useProject } from '../context/ProjectContext'
import { useToast } from '../context/ToastContext'
import { emptyLoan } from '../types/forms'
import type { LoanRequest, Guarantor } from '../types/forms'

const LOAN_TYPE_OPTIONS = [
  { value: 'Term', label: 'Term Loan' },
  { value: 'LOC', label: 'Line of Credit' },
  { value: 'CRE', label: 'Commercial Real Estate' },
  { value: 'SBA', label: 'SBA Loan' },
  { value: 'Bridge', label: 'Bridge Loan' },
]

const GUARANTOR_COLS = [
  { key: 'name', header: 'Name', placeholder: 'Guarantor name' },
  { key: 'relationship', header: 'Relationship', placeholder: 'e.g. Owner, Spouse' },
  { key: 'net_worth', header: 'Net Worth', placeholder: '$0' },
]

export default function LoanForm() {
  const [form, setForm] = useState<LoanRequest>(emptyLoan())
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const { refreshTree } = useProject()
  const toast = useToast()

  useEffect(() => {
    setLoading(true)
    getLoan()
      .then((data) => setForm({ ...emptyLoan(), ...data }))
      .catch(() => {/* first-run: no file yet */})
      .finally(() => setLoading(false))
  }, [])

  const set = <K extends keyof LoanRequest>(key: K, value: LoanRequest[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await saveLoan(form)
      await refreshTree()
      toast.success('Loan request saved to Loan Request/request.md')
    } catch {
      toast.error('Failed to save loan request. Check that the backend is running.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32">
        <span className="text-xs text-[#8d8d8d]">Loading…</span>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      {/* Credit Request */}
      <section>
        <h3 className="text-xs font-semibold text-[#525252] uppercase tracking-wider mb-4 pb-2 border-b border-[#e0e0e0]">
          Credit Request
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <FormField
            type="number"
            label="Loan Amount"
            required
            value={form.loan_amount}
            onChange={(v) => set('loan_amount', v)}
            placeholder="0.00"
            prefix="$"
          />
          <FormField
            type="select"
            label="Loan Type"
            required
            value={form.loan_type}
            onChange={(v) => set('loan_type', v)}
            options={LOAN_TYPE_OPTIONS}
          />
          <div className="col-span-2">
            <FormField
              type="textarea"
              label="Loan Purpose"
              required
              value={form.loan_purpose}
              onChange={(v) => set('loan_purpose', v)}
              placeholder="Describe how the loan proceeds will be used…"
              rows={3}
            />
          </div>
          <div className="col-span-2">
            <FormField
              type="text"
              label="Primary Repayment Source"
              value={form.repayment_source}
              onChange={(v) => set('repayment_source', v)}
              placeholder="e.g. Operating cash flow from rental income"
            />
          </div>
          <FormField
            type="number"
            label="Term Requested (months)"
            value={form.term_months}
            onChange={(v) => set('term_months', v)}
            placeholder="60"
          />
          <FormField
            type="number"
            label="Amortization (months)"
            value={form.amortization_months}
            onChange={(v) => set('amortization_months', v)}
            placeholder="240"
          />
          <div className="col-span-2">
            <FormField
              type="text"
              label="Desired Timing"
              value={form.desired_timing}
              onChange={(v) => set('desired_timing', v)}
              placeholder="e.g. Close within 30 days"
            />
          </div>
        </div>
      </section>

      {/* Collateral */}
      <section>
        <h3 className="text-xs font-semibold text-[#525252] uppercase tracking-wider mb-4 pb-2 border-b border-[#e0e0e0]">
          Collateral Offered
        </h3>
        <FormField
          type="list-builder"
          label="Collateral items"
          items={form.collateral_offered}
          onChange={(items) => set('collateral_offered', items)}
          placeholder="e.g. 123 Main St commercial property"
          addLabel="Add collateral"
        />
      </section>

      {/* Guarantors */}
      <section>
        <h3 className="text-xs font-semibold text-[#525252] uppercase tracking-wider mb-4 pb-2 border-b border-[#e0e0e0]">
          Guarantors
        </h3>
        <FormField
          type="table-builder"
          label="Personal guarantors"
          columns={GUARANTOR_COLS}
          rows={form.guarantors as Record<string, string | number>[]}
          onChange={(rows) => set('guarantors', rows as Guarantor[])}
          addLabel="Add guarantor"
        />
      </section>

      {/* Submit */}
      <div className="pt-2">
        <button
          type="submit"
          disabled={submitting}
          className="px-5 py-2 bg-[#0f62fe] text-white text-sm font-medium rounded hover:bg-[#0353e9] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? 'Saving…' : 'Save Loan Request'}
        </button>
      </div>
    </form>
  )
}
