import { useState, useEffect } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import FormField from './FormField'
import { getBorrower, saveBorrower } from '../api/forms'
import { useProject } from '../context/ProjectContext'
import { useToast } from '../context/ToastContext'
import { emptyBorrower } from '../types/forms'
import type { BorrowerProfile, OwnershipEntry, ManagementBio } from '../types/forms'

const ENTITY_OPTIONS = [
  { value: 'LLC', label: 'LLC' },
  { value: 'Corp', label: 'Corporation' },
  { value: 'LP', label: 'Limited Partnership' },
  { value: 'Sole Prop', label: 'Sole Proprietorship' },
  { value: 'Other', label: 'Other' },
]

const OWNERSHIP_COLS = [
  { key: 'name', header: 'Name', placeholder: 'Owner name' },
  { key: 'percent', header: '%', type: 'number' as const, placeholder: '0' },
  { key: 'role', header: 'Role', placeholder: 'e.g. CEO' },
]

export default function BorrowerForm() {
  const [form, setForm] = useState<BorrowerProfile>(emptyBorrower())
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const { refreshTree } = useProject()
  const toast = useToast()

  useEffect(() => {
    setLoading(true)
    getBorrower()
      .then((data) => setForm({ ...emptyBorrower(), ...data }))
      .catch(() => {/* first-run: no file yet, keep empty defaults */})
      .finally(() => setLoading(false))
  }, [])

  const set = <K extends keyof BorrowerProfile>(key: K, value: BorrowerProfile[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const addBio = () =>
    set('management_bios', [...form.management_bios, { name: '', bio: '' }])

  const updateBio = (i: number, field: keyof ManagementBio, value: string) =>
    set(
      'management_bios',
      form.management_bios.map((b, idx) => (idx === i ? { ...b, [field]: value } : b)),
    )

  const removeBio = (i: number) =>
    set('management_bios', form.management_bios.filter((_, idx) => idx !== i))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await saveBorrower(form)
      await refreshTree()
      toast.success('Borrower profile saved to Borrower/profile.md')
    } catch {
      toast.error('Failed to save borrower profile. Check that the backend is running.')
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
      {/* Business Information */}
      <section>
        <h3 className="text-xs font-semibold text-[#525252] uppercase tracking-wider mb-4 pb-2 border-b border-[#e0e0e0]">
          Business Information
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 sm:col-span-1">
            <FormField
              type="text"
              label="Business Name"
              required
              value={form.business_name}
              onChange={(v) => set('business_name', v)}
              placeholder="Acme Corp"
            />
          </div>
          <FormField
            type="select"
            label="Entity Type"
            required
            value={form.entity_type}
            onChange={(v) => set('entity_type', v)}
            options={ENTITY_OPTIONS}
          />
          <FormField
            type="text"
            label="Industry"
            value={form.industry}
            onChange={(v) => set('industry', v)}
            placeholder="e.g. Commercial Real Estate"
            hint="Include NAICS code if known"
          />
          <FormField
            type="number"
            label="Years in Business"
            value={form.years_in_business}
            onChange={(v) => set('years_in_business', v)}
            placeholder="0"
          />
          <div className="col-span-2">
            <FormField
              type="textarea"
              label="Address"
              value={form.address}
              onChange={(v) => set('address', v)}
              placeholder="123 Main St, City, State ZIP"
              rows={2}
            />
          </div>
          <FormField
            type="text"
            label="Website"
            value={form.website}
            onChange={(v) => set('website', v)}
            placeholder="https://"
          />
          <FormField
            type="text"
            label="Existing Banking Relationship"
            value={form.existing_banking_relationship}
            onChange={(v) => set('existing_banking_relationship', v)}
            placeholder="First National Bank — since 2018"
          />
        </div>
      </section>

      {/* Ownership Structure */}
      <section>
        <h3 className="text-xs font-semibold text-[#525252] uppercase tracking-wider mb-4 pb-2 border-b border-[#e0e0e0]">
          Ownership Structure
        </h3>
        <FormField
          type="table-builder"
          label="Owners"
          columns={OWNERSHIP_COLS}
          rows={form.ownership_structure as Record<string, string | number>[]}
          onChange={(rows) => set('ownership_structure', rows as OwnershipEntry[])}
          addLabel="Add owner"
        />
      </section>

      {/* Management Team */}
      <section>
        <h3 className="text-xs font-semibold text-[#525252] uppercase tracking-wider mb-4 pb-2 border-b border-[#e0e0e0]">
          Management Team
        </h3>
        <div className="space-y-4">
          {form.management_bios.map((bio, i) => (
            <div key={i} className="border border-[#e0e0e0] rounded p-3 space-y-2 bg-[#fafafa]">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  className="flex-1 px-3 py-2 text-sm text-[#161616] bg-white border border-[#8d8d8d] rounded focus:outline-none focus:ring-2 focus:ring-[#0f62fe] focus:border-transparent transition-colors"
                  value={bio.name}
                  onChange={(e) => updateBio(i, 'name', e.target.value)}
                  placeholder="Manager name"
                />
                <button
                  type="button"
                  className="p-2 text-[#8d8d8d] hover:text-[#da1e28] transition-colors"
                  onClick={() => removeBio(i)}
                  title="Remove"
                >
                  <Trash2 size={14} />
                </button>
              </div>
              <textarea
                className="w-full px-3 py-2 text-sm text-[#161616] bg-white border border-[#8d8d8d] rounded focus:outline-none focus:ring-2 focus:ring-[#0f62fe] focus:border-transparent transition-colors resize-none"
                rows={3}
                value={bio.bio}
                onChange={(e) => updateBio(i, 'bio', e.target.value)}
                placeholder="Brief professional biography…"
              />
            </div>
          ))}
          <button
            type="button"
            className="flex items-center gap-1 px-2 py-1 text-xs text-[#0f62fe] hover:bg-[#edf4ff] rounded transition-colors"
            onClick={addBio}
          >
            <Plus size={12} />
            Add team member
          </button>
        </div>
      </section>

      {/* Submit */}
      <div className="pt-2">
        <button
          type="submit"
          disabled={submitting}
          className="px-5 py-2 bg-[#0f62fe] text-white text-sm font-medium rounded hover:bg-[#0353e9] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? 'Saving…' : 'Save Borrower Profile'}
        </button>
      </div>
    </form>
  )
}
